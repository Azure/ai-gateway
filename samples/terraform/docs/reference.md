# Reference

Details for both [networking paths](../README.md#choose-your-networking-path).
Review the limitations before changing an existing deployment.

## File guide

| File | What it controls |
| --- | --- |
| [terraform.tfvars.example](../terraform.tfvars.example) | Template for your ignored `terraform.tfvars` |
| [profiles/private-connectivity.tfvars.json](../profiles/private-connectivity.tfvars.json) | Three private-connectivity settings (no secrets) |
| [variables.tf](../variables.tf) / [outputs.tf](../outputs.tf) | Inputs, validation, outputs |
| [ai-gateway.tf](../ai-gateway.tf) | Gateway, provider, catalog, aliases, runtime key, telemetry exporter |
| [foundry-models.tf](../foundry-models.tf) | Model account and versioned deployments |
| [foundry-agents.tf](../foundry-agents.tf) | Agent account/project, Storage, Premium ACR, connections |
| [main.tf](../main.tf) / [rbac.tf](../rbac.tf) | Naming, shared resource group, monitoring, role assignments |
| [private-network.tf](../private-network.tf) / [private-test-client.tf](../private-test-client.tf) | Optional VNet, private endpoints, DNS, probe VM |
| [scripts/Test-PrivateGateway.ps1](../scripts/Test-PrivateGateway.ps1) / [private-path-probe.py](../scripts/private-path-probe.py) | Private probe (wrapper sends the Python to the VM) |
| [scripts/Test-ModelAliases.ps1](../scripts/Test-ModelAliases.ps1) | Public test of every alias |
| [scripts/Get-GatewayMonitoring.ps1](../scripts/Get-GatewayMonitoring.ps1) / [monitoring.md](monitoring.md) | Read-only bounded OTLP readiness, linked managed groups, two-stage setup |
| [tests](../tests) | Offline Terraform and Python tests |
| [acceptance.md](acceptance.md) | Customer runtime checks, expected results and evidence boundaries |
| [versions.tf](../versions.tf) / [.terraform.lock.hcl](../.terraform.lock.hcl) | Provider versions and checksums (commit the lock file) |

## Inputs

Required values are in the [shared setup](../README.md#shared-setup).

| Input | Purpose and default |
| --- | --- |
| `environment_name` | Naming and tag label. Default `aigateway`. |
| `storage_public_network_access` | Default `Enabled`. Set `Disabled` if policy requires it. No private storage path is created. |
| `developer_principal_id` | Entra object ID for developer access. Empty means no developer roles. |
| `developer_principal_type` | `User`, `Group` or `ServicePrincipal`. Default `User`. |
| `publisher_name`, `project_display_name`, `project_description`, `tags` | Display metadata and tags |
| `private_network_address_prefix` | Private-path VNet IPv4 /16. Default `10.247.0.0/16`. Pick a non-overlapping range before creating the network. |
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
| `model_api_configuration` | API format and endpoints per alias; compatibility check for both sample probes |
| `project_endpoint`, `project_id` | Hosted-agent app setup (not a model-call URL) |
| `container_registry_endpoint`, `storage_account_name` | Image and artifact setup for the agent app |
| `resource_group_name` | The shared application group; excludes verified Azure-managed OTLP helper groups |
| `resource_groups` | Compatibility map: `gateway`, `models` and `agents` all contain that same group name |
| `gateway_id`, `foundry_models_id`, `application_insights_ids` | Resource and telemetry lookup |
| `gateway_monitoring` | Nonsecret actual OTLP endpoints/DCR, Insights and expected Log Analytics IDs; not proof of readiness/delivery |
| `private_endpoint_ids`, `private_test_vm_id`, `private_probe_configuration` | Private-path lookup (VM outputs only when the test client is enabled) |

Outputs do **not** include runtime key values or telemetry connection strings.
Services use managed identities. Get the key through your approved secret process.
Never put keys in `.tfvars`, terminal output or source control.

### Probe compatibility

Terraform supports more model APIs than the supplied test scripts. Both
`Test-ModelAliases.ps1` and `Test-PrivateGateway.ps1` test **every** alias through
`/default/models/openai/v1/chat/completions`. They require each alias to declare
`api_format = "OpenAIChatCompletions"` and include
`"/openai/v1/chat/completions"` in `endpoints`. The new
`model_api_configuration` output carries these values; incompatible or missing
metadata stops the test rather than skipping a model.

This is a necessary compatibility check, not proof that a model accepts every
parameter. The public test sends `messages` and expects `choices[0].message.content`.
The private test additionally uses `max_tokens = 8`, `temperature = 0`, and expects
the exact reply `OK`. The example GPT-4.1 models are the reference configuration.
Do not assume a reasoning model supports those parameters just because it exposes
Chat Completions.

For Responses-only models, embeddings, image generation or other APIs, supply a
model-specific test on the **same intended network path**, with the documented
request/response format and explicit success criteria for every alias. Do not
change the declared endpoints just to bypass this check. A format/parameter
rejection, content mismatch, quota error or token-limit `429` is not by itself a
DNS/private-network failure.

**Existing state without the new output:** use the normal reviewed plan/apply
flow with the unchanged input file and, for private deployments, the explicit
private profile. An output-only update should contain no resource actions. Stop
if unexpected resource changes appear; do not replay an old plan or apply an
unrelated repair just to run a test. These instructions do not refresh or modify
your existing state automatically.

## Networking

The [private connectivity path](private-connectivity.md) adds:

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

### Single-group consolidation

The root module now manages only `azapi_resource.resource_group["gateway"]`,
retaining its existing `rg-<environment_name>-<resource_token>-gateway` name.
Models, agents, Storage, ACR and both monitoring stacks share that group with
the gateway and optional network/test client. Child resources remain under their
service parents, and the custom role definition remains subscription-scoped with
only this group as its assignable scope. Region inputs are still independent;
sharing a group does not move resources to a different region.

**Monitoring exception:** gateway OTLP enablement also provisions linked,
Azure-managed monitoring resources/groups. The exact DCR-scoped publisher role
can live outside the application group. Final acceptance verifies the linkage,
managed-group owner, gateway principal and exact role; a managed-looking name
alone is never an exemption. See [monitoring ownership and setup](monitoring.md).

The legacy gateway has `prevent_destroy = true`: a replacement/destroy plan must
fail rather than silently remove a resource whose SKU cannot be recreated.
Keep the existing environment, location inputs and authoritative state. Do not
discard state or change the environment label to get a "fresh" gateway.

For an existing three-group deployment:

1. Preserve a protected state backup and coordinate all Terraform writers.
2. Review a fresh **full** plan with the original inputs and the explicit private
   profile. Changed parent IDs normally require backend replacements; removing
   the old group instances from the configuration also proposes their deletion.
   This code change does not perform an Azure resource move.
3. Choose and approve a supported resource move or a deliberate rebuild before
   applying. Generic CognitiveServices move support does not establish support
   with private endpoints. Rebuilds can lose Storage data, registry images and
   telemetry history. Existing global names and soft-deleted Foundry backends can
   prevent recreation; resolve these explicitly, never by automatic purge.
4. Reconcile changed identities, resource-scoped roles, connection IDs and private
   endpoint targets. A private endpoint cannot change its target service in place.
   The replacement trigger covers known target changes, but AzAPI 2.13 skips
   reference triggers when its body contains unknown values, including a newly
   recreated account's ID. For this consolidation, the full plan **must** include
   `-replace='azapi_resource.private_endpoint["models"]'` alongside the explicit
   private profile. Confirm the Models endpoint is replaced, not updated, before
   approving any apply. Preserve the AIGateway API/authentication and network
   settings. Reject any unexpected gateway or network replacement.
5. Verify private inference and telemetry before cleanup. **Do not apply a plan
   deleting either old group** until every contained resource is accounted for
   and its removal is approved. Azure group deletion can remove resources not
   tracked by Terraform. A successful but empty generic inventory is not enough
   when direct resource GETs still find resources.

The legacy `resource_groups` output keys remain available for scripts, but now
resolve to the same name. A plan against the old layout is not an output-only
update. Offline tests establish placement and contracts, not migration safety.

For an approved rebuild, set a stable `backend_revision` in your deployment
inputs to generate fresh backend names without changing the gateway or group.
Keep that revision for subsequent deployments; changing or removing it causes
another replacement. The default empty revision preserves existing names.

Set `retain_legacy_resource_groups = true` only during migration to keep the old
groups managed until backend acceptance. It does not place any new service in
those groups. After verifying their contents and approving cleanup, set it back
to `false` and review a new full plan before applying the two group deletions.
The normal final configuration manages exactly one group.

## Offline checks

No Azure resources or authentication needed. Use a clean checkout without
deployment tfvars/state. The local/CI entrypoint includes every regression suite:

```powershell
.\scripts\Test-Offline.ps1
```

The Terraform tests use mocked AzAPI; script tests stub network/CLI calls. They
check shared-group placement, preserved monitoring/output contracts, model/API metadata and token-limit wiring, gateway location, identity-based
backends, opt-in developer roles, invalid inputs, the private profile, and rejection
of unsupported probe APIs. Python 3 and PowerShell 7 are required for the script
tests. These are **not** runtime tests. For actual acceptance, use the
[customer acceptance guide](acceptance.md).

## Implementation notes

- Follows the upstream [Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra) and a [model-registration fix](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/commit/03fcd3788aea06cf6000af19890f8164303348d5).
- AzAPI defines the preview ARM resources directly. Model operations are serialized per account with locks. The automatic gateway `default` workspace is referenced, not recreated.
- Token policies use `["identity"]`, not the older scalar `"Identity"` key.
- AzAPI 2.13 has no bundled schemas for several preview resources, so those blocks set `schema_validation_enabled = false`. ARM still validates them at deploy time. Offline success does not prove preview access, capacity or API acceptance.

## Limitations

General constraints checked **October 19, 2026**; resource-type lifecycle below
checked **October 22, 2026**. Preview features can change. Recheck the official
sources before changing or replacing a deployment.

### Resource type and lifecycle

This sample keeps `Microsoft.ApiManagement/service@2025-09-01-preview` with SKU
`AIGateway`. According to the [Microsoft migration guide](https://learn.microsoft.com/azure/api-management/ai-gateway-resource):

- New resources with this legacy SKU can no longer be created.
- Existing resources must migrate **before January 15, 2027** and are permanently
  removed after retirement.
- The replacement `Microsoft.ApiManagement/aigateways` is a different resource
  type and requires a new gateway, not an in-place API-version edit.
- The replacement currently does **not** support gateway private endpoints.
  The private-connectivity instructions here describe the retained legacy
  resource, not the replacement.

No API-version change or migration is implemented by this sample. Its networking
paths document the existing configuration, not a recommendation for new legacy
deployments.

### Microsoft-documented constraints

- **AI Gateway preview:** best-effort, **no SLA**. APIs, limits, regions and pricing can change. Documented regions include East US 2 and Sweden Central, with access varying by subscription. ([overview](https://learn.microsoft.com/azure/api-management/ai-gateway-overview))
- **Hosted-agent VNet injection is set at account creation** and cannot be added later. This sample does not configure it. If you need private agent execution, choose a supported network-secured Foundry setup before creating the account. ([Foundry networking limits](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations))
- **Private endpoints can be added later** to an existing legacy `service`/`AIGateway` resource, with outbound integration configured separately. Private endpoints alone do not give the gateway or agents outbound access. This does not establish support on the replacement `aigateways` resource. ([private networking](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking))
- **Private ACR image pulls** are supported for Foundry projects created after June 25, 2026. Older projects need public ACR reachability. This sample leaves ACR public.

### Known blocker: private-only gateway ingress

**Status: Pending - product-group investigation (October 23, 2026).** Resolution
of the observed public-disable failure is being clarified with the product group.
No fix has been verified for this public-preview sample yet. The current profile
therefore keeps gateway public access enabled; this status is not a promise of
private-only access or a confirmed permanent product limitation.

**Observed in our tests, not a universal SKU limit.** Microsoft [documents disabling public access after private connectivity is verified](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking#inbound-private-link). In our **October 18, 2026, Sweden Central** tests:

- Both aliases passed private DNS and inference checks with model public access disabled (ACL Deny).
- Disabling gateway public access failed with `UpdateApiServiceFailed`, through both Terraform and the CLI's public-access PATCH. Private access kept working, but public access stayed on.
- A minimal gateway in the same subscription and region reproduced the failure. Its private endpoint still worked. Test resources were deleted.

Root cause is unknown. Do not set gateway public access to `Disabled` in this PoC or describe it as private-only.

Before this pending item can be closed, a private-only version must show:

1. The gateway reports `Disabled`.
2. Every alias works privately.
3. A previously working valid-key public call gets a network rejection (not just a 401).
4. The planned end state has no pending changes.

No automatic recovery or destructive workaround is included.

## Cost and cleanup

Both paths create billable resources. Model calls, Premium ACR, Storage and
monitoring all cost money. Deallocate the optional VM as described in
[private connectivity](private-connectivity.md#step-6-stop-the-vm-when-you-are-done);
stopping the VM does not stop the other charges.

The gateway has `prevent_destroy = true`: an ordinary full `terraform destroy`
is intentionally blocked. Do not remove this protection, remove resources from
state or delete the group to work around it. This legacy gateway might not be
recreatable. Full teardown needs explicit approval for permanent gateway/data
loss, exact resource inventory (including resources not managed by this state),
state backup and a separately reviewed protection change and destroy plan.
Keep the private profile and all original inputs on that plan. If retaining the
gateway, design and review a partial teardown with its owner instead; there is
no universally safe one-command cleanup. Acceptance automation never destroys
resources or removes the protection.

## References

- [Upstream Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra)
- [AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest/docs)
- [AI Gateway overview](https://learn.microsoft.com/azure/api-management/ai-gateway-overview)
- [AI Gateway private networking](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking)
- [Foundry Agent Service networking](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations)
- [Model and tool management](https://learn.microsoft.com/azure/api-management/ai-gateway-manage-models-tools)
