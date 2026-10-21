# Reference

Look up details here as needed. You do not need to read this to deploy.

## File guide

| File | What it controls |
| --- | --- |
| [terraform.tfvars.example](../terraform.tfvars.example) | Template for your ignored `terraform.tfvars` |
| [profiles/private-connectivity.tfvars.json](../profiles/private-connectivity.tfvars.json) | Three private-connectivity settings (no secrets) |
| [variables.tf](../variables.tf) / [outputs.tf](../outputs.tf) | Inputs, validation, outputs |
| [ai-gateway.tf](../ai-gateway.tf) | Gateway, provider, catalog, aliases, runtime key, telemetry exporter |
| [foundry-models.tf](../foundry-models.tf) | Model account and versioned deployments |
| [foundry-agents.tf](../foundry-agents.tf) | Agent account/project, Storage, Premium ACR, connections |
| [main.tf](../main.tf) / [rbac.tf](../rbac.tf) | Naming, resource groups, monitoring, role assignments |
| [private-network.tf](../private-network.tf) / [private-test-client.tf](../private-test-client.tf) | Optional VNet, private endpoints, DNS, probe VM |
| [scripts/Test-PrivateGateway.ps1](../scripts/Test-PrivateGateway.ps1) / [private-path-probe.py](../scripts/private-path-probe.py) | Private probe (wrapper sends the Python to the VM) |
| [scripts/Test-ModelAliases.ps1](../scripts/Test-ModelAliases.ps1) | Public test of every alias |
| [tests](../tests) | Offline Terraform and Python tests |
| [versions.tf](../versions.tf) / [.terraform.lock.hcl](../.terraform.lock.hcl) | Provider versions and checksums (commit the lock file) |

## Inputs

Required values are in the [quick start](../README.md#quick-start-public-endpoints).

| Input | Purpose and default |
| --- | --- |
| `environment_name` | Naming and tag label. Default `aigateway`. |
| `storage_public_network_access` | Default `Enabled`. Set `Disabled` if policy requires it. No private storage path is created. |
| `developer_principal_id` | Entra object ID for developer access. Empty means no developer roles. |
| `developer_principal_type` | `User`, `Group` or `ServicePrincipal`. Default `User`. |
| `publisher_name`, `project_display_name`, `project_description`, `tags` | Display metadata and tags |
| `private_network_address_prefix` | Path B VNet IPv4 /16. Default `10.247.0.0/16`. Pick a non-overlapping range before the first deploy. |
| `enable_private_test_client` | Default `false`. Requires private networking. |
| `private_test_client_ssh_public_key` | OpenSSH **public** key, required when the VM is created |
| `private_test_client_vm_size` | Default `Standard_B2s_v2`. Check availability and quota. |

**Each `model_deployments` entry** requires `model_name`, `model_version`, `capacity`, and `token_limit`.

- `capacity` is a quota unit specific to the model SKU.
- `token_limit` is the gateway's tokens-per-minute limit per identity.
- They are independent. Do not convert one to the other.

Optional fields: `model_format`, `sku_name`, `api_format`, `endpoints`, `description`. Match the API format and endpoints to the model. See [variables.tf](../variables.tf) for types and validation.

## Outputs

| Output | Use it for |
| --- | --- |
| `gateway_endpoint` | Base URL for runtime calls |
| `gateway_api_key_id` | ARM ID for retrieving the key. **Not the key value.** |
| `model_deployment_ids` | Model IDs keyed by alias |
| `project_endpoint`, `project_id` | Hosted-agent app setup (not a model-call URL) |
| `container_registry_endpoint`, `storage_account_name` | Image and artifact setup for the agent app |
| `resource_groups`, `gateway_id`, `foundry_models_id`, `application_insights_ids` | Resource and telemetry lookup |
| `private_endpoint_ids`, `private_test_vm_id`, `private_probe_configuration` | Path B lookup (VM outputs only when the test client is enabled) |

Outputs do **not** include runtime key values or telemetry connection strings.
Services use managed identities. Get the key through your approved secret process.
Never put keys in `.tfvars`, terminal output or source control.

## Networking

Path B adds:

- A VNet with an outbound integration subnet delegated to `Microsoft.Web/serverFarms`
- Separate endpoint and client subnets
- Two private endpoints (gateway group `Gateway`, model group `account`)
- Four private DNS zones

Tested gateway contract: `2025-09-01-preview` with `virtualNetworkType = "External"`.
Inbound Private Link and outbound integration solve different problems. Neither replaces the other.

The optional Ubuntu VM has no public IP, denies inbound traffic, and has a narrow custom role for reading the gateway key. Its subnet allows default outbound internet for VM agent and ARM operations, so it is not air-gapped.

**Not configured:** corporate DNS, peering, VPN, forced tunneling, and custom firewall rules. Review the [official networking guide](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking) for same-region subnets, DNS and NSG requirements.

Disabling the feature flag can destroy network resources. Review that change separately. This network does not isolate the agent account, Storage or ACR.

## State and security

- **Local state** is used here. State and plans can contain sensitive data, including telemetry connection strings. Restrict access and never commit them. `.gitignore` covers state, plans, provider downloads and user `.tfvars`.
- For shared or production use, move to a remote backend with encryption and locking (for example, Azure Blob Storage with Entra auth). Migrate with `terraform init -migrate-state`.
- Storage blocks anonymous blobs and shared keys. ACR admin users and Foundry local auth are disabled. Gateway payload capture is disabled.
- Keep policy-required storage restrictions. Private hosted-agent storage access is **not** verified here.
- Project roles mirror the upstream Bicep, including Cognitive Services Contributor. Developer access also grants Storage Blob Data Contributor. Enable it on purpose and review least privilege.

## Offline checks

No Azure resources or authentication needed:

```powershell
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

These use mocked AzAPI. They check model, endpoint and token-limit wiring, gateway location, identity-based backends, opt-in developer roles, invalid inputs, and the private profile. They are **not** runtime tests.

## Implementation notes

- Follows the upstream [Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra) and a [model-registration fix](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/commit/03fcd3788aea06cf6000af19890f8164303348d5).
- AzAPI defines the preview ARM resources directly. Model operations are serialized per account with locks. The automatic gateway `default` workspace is referenced, not recreated.
- Token policies use `["identity"]`, not the older scalar `"Identity"` key.
- AzAPI 2.13 has no bundled schemas for several preview resources, so those blocks set `schema_validation_enabled = false`. ARM still validates them at deploy time. Offline success does not prove preview access, capacity or API acceptance.

## Limitations

Documentation checked **October 19, 2026**. Preview features can change. Recheck the official sources before deploying.

### Microsoft-documented constraints

- **AI Gateway preview:** best-effort, **no SLA**. APIs, limits, regions and pricing can change. Documented regions include East US 2 and Sweden Central, with access varying by subscription. ([overview](https://learn.microsoft.com/azure/api-management/ai-gateway-overview))
- **Hosted-agent VNet injection is set at account creation** and cannot be added later. This sample does not configure it. If you need private agent execution, choose a supported network-secured Foundry setup before creating the account. ([Foundry networking limits](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations))
- **Private endpoints can be added later** to an existing gateway, with outbound integration configured separately. Private endpoints alone do not give the gateway or agents outbound access. ([private networking](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking))
- **Private ACR image pulls** are supported for Foundry projects created after June 25, 2026. Older projects need public ACR reachability. This sample leaves ACR public.

### Known blocker: private-only gateway ingress

**Observed in our tests, not a universal SKU limit.** Microsoft [documents disabling public access after private connectivity is verified](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking#inbound-private-link). In our **October 18, 2026, Sweden Central** tests:

- Both aliases passed private DNS and inference checks with model public access disabled (ACL Deny).
- Disabling gateway public access failed with `UpdateApiServiceFailed`, through both Terraform and the CLI's public-access PATCH. Private access kept working, but public access stayed on.
- A minimal gateway in the same subscription and region reproduced the failure. Its private endpoint still worked. Test resources were deleted.

Root cause is unknown. Do not set gateway public access to `Disabled` in this PoC or describe it as private-only.

A future private-only version must show:

1. The gateway reports `Disabled`.
2. Every alias works privately.
3. A previously working valid-key public call gets a network rejection (not just a 401).
4. The planned end state has no pending changes.

No automatic recovery or destructive workaround is included.

## Cost and cleanup

Both paths create billable resources. Model calls, Premium ACR, Storage, and monitoring all cost money. To tear down, run `terraform destroy` after reviewing the plan. Stop the optional VM as described in [private connectivity](private-connectivity.md#step-6-stop-the-vm-when-you-are-done) if you want to keep the rest.

## References

- [Upstream Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra)
- [AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest/docs)
- [AI Gateway overview](https://learn.microsoft.com/azure/api-management/ai-gateway-overview)
- [AI Gateway private networking](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking)
- [Foundry Agent Service networking](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations)
- [Model and tool management](https://learn.microsoft.com/azure/api-management/ai-gateway-manage-models-tools)
