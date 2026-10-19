variable "subscription_id" {
  description = "Azure subscription in which to provision the three resource groups."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a UUID."
  }
}

variable "environment_name" {
  description = "Short environment label used in resource group names and tags."
  type        = string
  default     = "aigateway"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,31}$", var.environment_name))
    error_message = "Use 1-32 lowercase letters, numbers, or hyphens, starting with a letter."
  }
}

variable "location" {
  description = "Region supporting Foundry hosted agents, the selected models, storage, ACR, and monitoring. Confirm availability before applying."
  type        = string
  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "location must not be empty."
  }
}

variable "gateway_location" {
  description = "Region in which the subscription is enabled for the preview AIGateway SKU."
  type        = string
  validation {
    condition     = length(trimspace(var.gateway_location)) > 0
    error_message = "gateway_location must not be empty."
  }
}

variable "storage_public_network_access" {
  description = "Storage public network access. Use Disabled when required by Azure Policy; private connectivity must then be provided separately for hosted agents."
  type        = string
  default     = "Enabled"
  validation {
    condition     = contains(["Enabled", "Disabled"], var.storage_public_network_access)
    error_message = "storage_public_network_access must be Enabled or Disabled."
  }
}

variable "enable_private_networking" {
  description = "Create gateway/model private endpoints, DNS, and gateway outbound VNet integration. Hosted-agent networking is not changed."
  type        = bool
  default     = false
}

variable "private_network_address_prefix" {
  description = "Non-overlapping IPv4 /16 for the optional PoC VNet; three /24 subnets are derived from it."
  type        = string
  default     = "10.247.0.0/16"
  validation {
    condition     = can(cidrnetmask(var.private_network_address_prefix)) && endswith(var.private_network_address_prefix, "/16")
    error_message = "private_network_address_prefix must be a valid IPv4 /16."
  }
}

variable "gateway_public_network_access" {
  description = "Keep Enabled for the private-connectivity PoC. Disabled requests private-only ingress and requires separate live validation; see the observed preview limitation."
  type        = string
  default     = "Enabled"
  validation {
    condition = (
      contains(["Enabled", "Disabled"], var.gateway_public_network_access) &&
      (var.gateway_public_network_access != "Disabled" || var.enable_private_networking)
    )
    error_message = "Use Enabled or Disabled; disabling requires enable_private_networking."
  }
}

variable "models_public_network_access" {
  description = "Keep Enabled until gateway outbound private connectivity is ready, then set Disabled and retest."
  type        = string
  default     = "Enabled"
  validation {
    condition = (
      contains(["Enabled", "Disabled"], var.models_public_network_access) &&
      (var.models_public_network_access != "Disabled" || var.enable_private_networking)
    )
    error_message = "Use Enabled or Disabled; disabling requires enable_private_networking."
  }
}

variable "enable_private_test_client" {
  description = "Create a billable private Ubuntu test VM with outbound-only internet, no public IP and narrowly scoped API-key retrieval access."
  type        = bool
  default     = false
  validation {
    condition     = !var.enable_private_test_client || var.enable_private_networking
    error_message = "The private test client requires enable_private_networking."
  }
}

variable "private_test_client_ssh_public_key" {
  description = "OpenSSH public key required only when the test VM is enabled. No private key or password belongs in Terraform."
  type        = string
  default     = ""
  validation {
    condition = (
      !var.enable_private_test_client ||
      can(regex("^ssh-(ed25519|rsa) [A-Za-z0-9+/=]+( .*)?$", trimspace(var.private_test_client_ssh_public_key)))
    )
    error_message = "Supply an OpenSSH ed25519 or RSA public key when enabling the private test client."
  }
}

variable "private_test_client_vm_size" {
  description = "Small test VM SKU; verify regional quota and availability before enabling."
  type        = string
  default     = "Standard_B2s_v2"
}

variable "publisher_email" {
  description = "Publisher contact email for the API Management gateway."
  type        = string
  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.publisher_email))
    error_message = "publisher_email must be an email address."
  }
}

variable "publisher_name" {
  description = "Publisher display name for the gateway."
  type        = string
  default     = "AI Gateway"
}

variable "model_deployments" {
  description = "Foundry deployments keyed by ARM-safe deployment name. Select model versions, deployment SKUs, and quota available to your subscription."
  type = map(object({
    model_name    = string
    model_version = string
    model_format  = optional(string, "OpenAI")
    sku_name      = optional(string, "GlobalStandard")
    capacity      = number
    token_limit   = number
    api_format    = optional(string, "OpenAIChatCompletions")
    endpoints     = optional(list(string), ["/openai/v1/chat/completions", "/openai/v1/responses"])
    description   = optional(string, "Foundry model routed through AI Gateway.")
  }))
  validation {
    condition = length(var.model_deployments) > 0 && alltrue([
      for name, model in var.model_deployments :
      can(regex("^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$", name)) &&
      length(trimspace(model.model_name)) > 0 &&
      length(trimspace(model.model_version)) > 0 &&
      model.capacity >= 1 && floor(model.capacity) == model.capacity &&
      model.token_limit >= 1 && floor(model.token_limit) == model.token_limit &&
      length(model.endpoints) > 0
    ])
    error_message = "Provide at least one model with an ARM-safe name, explicit model name/version, positive integer capacity/token_limit, and at least one endpoint."
  }
}

variable "developer_principal_id" {
  description = "Optional Entra object ID for development access. Empty disables all developer role assignments."
  type        = string
  default     = ""
  validation {
    condition     = var.developer_principal_id == "" || can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.developer_principal_id))
    error_message = "developer_principal_id must be empty or a UUID."
  }
}

variable "developer_principal_type" {
  description = "Entra principal type for optional development access."
  type        = string
  default     = "User"
  validation {
    condition     = contains(["User", "Group", "ServicePrincipal"], var.developer_principal_type)
    error_message = "Use User, Group, or ServicePrincipal."
  }
}

variable "project_display_name" {
  description = "Display name for the Foundry hosted-agent project."
  type        = string
  default     = "AI Gateway hosted agents"
}

variable "project_description" {
  description = "Description of the hosted-agent project."
  type        = string
  default     = "Hosted-agent infrastructure with a separate Foundry model account and AI Gateway."
}

variable "tags" {
  description = "Additional tags for supported Azure resources."
  type        = map(string)
  default     = {}
}
