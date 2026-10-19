terraform {
  required_version = ">= 1.11.0, < 2.0.0"

  required_providers {
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.13.0"
    }
  }
}

provider "azapi" {
  subscription_id = var.subscription_id
}
