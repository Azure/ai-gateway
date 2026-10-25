variable "subscription_id" {
  description = "Azure subscription containing the shared resource group."
  type        = string
  validation {
    condition     = can(regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", var.subscription_id))
    error_message = "subscription_id must be a UUID."
  }
}

variable "gateway_access_principals" {
  description = "Optional caller identities granted AI Gateway Models User at gateway scope. Additive Entra access for all gateway models; API keys and existing agent/test-VM authentication remain unchanged."
  type = map(object({
    principal_id   = string
    principal_type = optional(string, "ServicePrincipal")
  }))
  default  = {}
  nullable = false
  validation {
    condition = alltrue([for principal in var.gateway_access_principals : try(
      can(regex("(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", principal.principal_id)) &&
      contains(["User", "Group", "ServicePrincipal"], principal.principal_type), false
    )])
    error_message = "Each gateway caller requires an Entra object UUID and principal_type User, Group or ServicePrincipal."
  }
  validation {
    condition = try(
      length(distinct([for principal in var.gateway_access_principals : lower(principal.principal_id)])) == length(var.gateway_access_principals),
      false
    )
    error_message = "Each gateway caller object ID must appear only once, regardless of letter case."
  }
}

variable "environment_name" {
  description = "Short environment label used in the shared resource group name and tags."
  type        = string
  default     = "aigateway"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,31}$", var.environment_name))
    error_message = "Use 1-32 lowercase letters, numbers, or hyphens, starting with a letter."
  }
}

variable "backend_revision" {
  description = "Optional stable revision for deliberate backend recreation with fresh names. Does not rename the gateway or shared group. Changing it replaces backend resources."
  type        = string
  default     = ""
  validation {
    condition     = var.backend_revision == "" || can(regex("^[a-z0-9][a-z0-9-]{0,31}$", var.backend_revision))
    error_message = "backend_revision must be empty or 1-32 lowercase letters, digits or hyphens, starting with a letter or digit."
  }
}

variable "retain_legacy_resource_groups" {
  description = "Migration-only safety switch: retain the old empty Models/Agents groups during backend rebuild. Set false after acceptance and inventory review; new resources always use the gateway group."
  type        = bool
  default     = false
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
  description = "Create gateway/model private endpoints, DNS, and gateway outbound VNet integration. Does not by itself enable private hosted-agent execution."
  type        = bool
  default     = false
}

variable "enable_private_hosted_agent" {
  description = "Add a separate private Foundry account/project with Basic VNet injection, delegated subnet and private registry access. Keeps the original agent account and outputs unchanged; does not deploy an agent."
  type        = bool
  default     = false
  validation {
    condition = !var.enable_private_hosted_agent || (
      var.enable_private_networking && lower(var.location) == lower(var.gateway_location)
    )
    error_message = "Private hosted agents require private networking and the same Foundry/VNet region (location must equal gateway_location)."
  }
  validation {
    condition = !var.enable_private_hosted_agent || can(regex(
      "^(10\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.|192\\.168\\.)", var.private_network_address_prefix
    ))
    error_message = "The private hosted-agent VNet must use RFC1918 IPv4 address space."
  }
}

variable "private_hosted_agent_runtime_principal_id" {
  description = "Optional actual managed-identity object ID discovered after private agent deployment. Grants gateway key retrieval at gateway scope only; never supply the old agent identity as a placeholder."
  type        = string
  default     = ""
  validation {
    condition = var.private_hosted_agent_runtime_principal_id == "" || (
      var.enable_private_hosted_agent &&
      can(regex("(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.private_hosted_agent_runtime_principal_id))
    )
    error_message = "Supply an actual Entra object UUID only when enable_private_hosted_agent is true, or leave the runtime principal empty."
  }
}

variable "private_network_address_prefix" {
  description = "Non-overlapping IPv4 /16 for the optional PoC VNet; three /24 subnets, plus subnet index 3 for optional private hosted agents, are derived from it."
  type        = string
  default     = "10.247.0.0/16"
  validation {
    condition     = can(cidrnetmask(var.private_network_address_prefix)) && endswith(var.private_network_address_prefix, "/16")
    error_message = "private_network_address_prefix must be a valid IPv4 /16."
  }
}

variable "gateway_public_network_access" {
  description = "Gateway public ingress. For an existing gateway, select Disabled after private endpoint approval and private-route verification; preserve that end state on subsequent plans. First-create and Terraform update behavior require live validation."
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

variable "gateway_private_endpoint_manual_approval" {
  description = "Use a separately named manual-request gateway endpoint and approve it after creation. Changing this replaces only the gateway private endpoint; review migration first."
  type        = bool
  default     = false
  validation {
    condition     = !var.gateway_private_endpoint_manual_approval || var.enable_private_networking
    error_message = "Manual gateway endpoint approval requires enable_private_networking."
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
