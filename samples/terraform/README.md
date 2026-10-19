# AI Gateway and Foundry infrastructure with Terraform

Provision the three infrastructure building blocks used by the
[Foundry AI Gateway Python sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway):
AI Gateway, a dedicated Foundry model account, and a separate Foundry hosted-agent
account/project. This is a standalone Terraform sample, not an `azd` application.

The configuration follows the upstream
[Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra).
It uses the AzAPI provider to express the preview ARM resources directly.
The current token-policy shape and runtime model aliases incorporate the
[upstream model-registration fix](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/commit/03fcd3788aea06cf6000af19890f8164303348d5).

## What is provisioned

| Building block | Resources |
| --- | --- |
| [AI Gateway](ai-gateway.tf) | API Management with the **AIGateway** SKU and system-assigned identity, connector gateway, Foundry model provider, model catalog entries with per-identity token limits, runtime model aliases, runtime API key resource, and Application Insights telemetry exporter. |
| [Foundry Models](foundry-models.tf) | Separate AI Services account with local authentication disabled and explicitly versioned model deployments. The gateway identity receives Foundry User access on this account. |
| [Foundry Hosted Agent infrastructure](foundry-agents.tf) | Project-enabled AI Services account, project identity, Storage, Premium Container Registry, project connections, and agent tracing through Application Insights. |
| [Shared resources](main.tf) and [RBAC](rbac.tf) | Three resource groups, separate gateway/agent Log Analytics workspaces and Application Insights components, project access to its account/storage/registry, and optional developer access. |
| Optional [private-connectivity PoC profile](#private-connectivity-poc-profile) | Gateway/model private endpoints and DNS, gateway outbound VNet integration, private model access, and an optional private test client. Keeps the dedicated AIGateway SKU and explicitly leaves gateway public access enabled. |

Model operations are serialized per account using AzAPI resource locks. The
gateway's automatically created `default` workspace is referenced rather than
created a second time.
Each catalog entry has a matching workspace alias; the alias is required to route
runtime requests to the model. Token policies use the current `["identity"]`
counter-key format rather than the older scalar `"Identity"` format.

**Infrastructure only:** this does not build/push an agent image, create an agent
definition, start a hosted-agent container, register GitHub MCP tools, configure
GitHub credentials, or create a daily-digest schedule. Use the end-to-end sample
for application setup after provisioning. It does not replace its `azd` hooks or
produce an `azd` environment.

## Prerequisites

- Terraform **1.11 or later**, below 2.0, and Azure CLI.
- An Azure subscription enabled for the **preview AIGateway tier** and Foundry
  hosted agents in your selected regions. The gateway region is independent from
  the Foundry region.
- Permission to create resource groups/resources and role assignments at their
  scopes, such as Contributor plus Role Based Access Control Administrator,
  subject to your organization's policies.
- Registered providers: `Microsoft.ApiManagement`, `Microsoft.Web`,
  `Microsoft.CognitiveServices`, `Microsoft.Storage`, `Microsoft.ContainerRegistry`,
  `Microsoft.OperationalInsights`, and `Microsoft.Insights`. This sample does not
  register providers on your behalf.
- Available model versions and sufficient deployment quota for the selected
  model SKU/region. Example values are illustrative, not an availability promise.

Confirm preview access, model availability, and organizational network policies
before applying. Region/model availability is not inferred by this configuration.

## Configure and provision

Run from this directory in PowerShell:

```powershell
az login
Copy-Item terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: subscription, regions, publisher, model versions, and quota.
az account set --subscription "<subscription-id-from-terraform.tfvars>"

terraform init
terraform fmt -check -recursive
terraform validate
terraform plan "-out=deployment.tfplan"
terraform apply "deployment.tfplan"
```

Review the plan before applying. These commands create billable resources,
including the Foundry deployments, Premium ACR, Storage, and monitoring.
Preview pricing/terms and access requirements must be checked separately.

Names are derived from the subscription, environment name, and Foundry region.
Use a different `environment_name` for another environment. Changing those
inputs can replace resources. This configuration creates new infrastructure;
it does not automatically adopt resources provisioned by Bicep.

### Inputs

| Input | Required | Meaning |
| --- | --- | --- |
| `subscription_id` | Yes | Target subscription UUID; also supplied explicitly to the provider. |
| `location` | Yes | Foundry, storage, registry, and monitoring region. |
| `gateway_location` | Yes | Region enabled for your AIGateway preview deployment. |
| `storage_public_network_access` | No | `Enabled` by default; set `Disabled` to preserve a policy-required restriction. This sample does not create private storage connectivity. |
| `publisher_email` | Yes | Gateway publisher contact. |
| `model_deployments` | Yes | Map keyed by deployment/catalog name. Each model needs `model_name`, `model_version`, positive integer `capacity`, and `token_limit`. |
| `environment_name` | No | Naming/tagging label; defaults to `aigateway`. |
| `developer_principal_id` | No | Entra object ID for optional developer access; omitted by default. |
| `developer_principal_type` | No | `User`, `Group`, or `ServicePrincipal`; defaults to `User`. |
| `publisher_name`, `project_display_name`, `project_description`, `tags` | No | Display metadata and additional resource tags. |

`capacity` is the model deployment's SKU-specific quota unit; `token_limit` is
the gateway's per-identity tokens-per-minute limit. They are independent inputs,
not a universal conversion. Each model can also override `model_format`,
`sku_name`, `api_format`, `endpoints`, and `description`; see
[variables.tf](variables.tf). Match endpoints/API format to each model's capabilities.

### Outputs and credentials

`terraform output` exposes resource group names, gateway ID/endpoint, the runtime
API key **resource ID**, model deployment IDs, project ID/endpoint, registry login
server, storage name, and monitoring resource IDs. It does not export runtime
key values or telemetry connection strings.

Foundry backend access, storage, and image pulls use managed identities. The
runtime API key resource is created for applications that authenticate to the
gateway with a key; retrieve and store its value through your approved secret
management process rather than committing it to a `.tfvars` file.

## State and security

- This demonstration starts with **local state**. State and saved plans can
  contain sensitive resource responses, including telemetry connection strings
  and API responses. Restrict filesystem access and do not commit them.
  `.gitignore` excludes local state, plans, provider downloads, and user `.tfvars`.
  The only committed `.tfvars.json` exception is the non-secret PoC profile;
  keep subscription-specific inputs and credentials out of it. Retain
  `.terraform.lock.hcl` to pin provider checksums.
- Before shared or production use, configure an access-controlled remote backend
  with encryption/locking, such as Azure Blob Storage with Entra authentication,
  and migrate local state using `terraform init -migrate-state`.
- Like the upstream sample, the default uses **public network endpoints**. Optional
  private gateway/model networking is described below; hosted-agent networking
  remains separate. This is not a private-network production baseline. Storage forbids anonymous blobs and shared
  keys; ACR admin credentials and Foundry local authentication are disabled.
- If Azure Policy disables storage public access, set
  `storage_public_network_access = "Disabled"` rather than overriding the policy.
  Gateway/model testing can proceed independently, but hosted-agent storage
  connectivity remains unverified until a policy-compliant private network path
  is configured separately.
- Project account roles mirror the upstream Bicep, including Cognitive Services
  Contributor. Optional developer access grants those account roles and Storage
  Blob Data Contributor. Enable it only deliberately and review least privilege.
- Gateway telemetry payload capture is disabled.

## Private-connectivity PoC profile

Use [profiles/private-connectivity.tfvars.json](profiles/private-connectivity.tfvars.json)
to select the dedicated-SKU configuration proven in the sandbox:

```text
Private client -> gateway private endpoint -> private model endpoint
```

| Setting | Profile value |
| --- | --- |
| `enable_private_networking` | `true` |
| `gateway_public_network_access` | `Enabled` |
| `models_public_network_access` | `Disabled` |

The profile reuses the resources in this root rather than creating a second
gateway: gateway/model private endpoints and DNS, outbound VNet integration,
gateway managed identity and Foundry User binding, API-key resource, and
Application Insights telemetry with payload capture disabled. Model local
authentication is disabled and its network ACL becomes Deny.

**Not private-only ingress:** clients can use the gateway private endpoint,
but the public gateway endpoint remains reachable with valid credentials.
The profile does not claim to fix the public-disablement failure documented
below. Hosted-agent networking is unchanged and agent execution is not proven.

Keep subscription, environment, regions, model choices, policy-compatible storage
settings and other personal inputs in your ignored `terraform.tfvars`. Pass this
profile explicitly with `-var-file`; it is not auto-loaded and does not change
the default public sample. It overrides the three settings above from
`terraform.tfvars` and any `*.auto.tfvars`, including a private-only override.
Review that deliberate gateway-public-access choice before applying. Later
`-var` or `-var-file` arguments can override the profile.

For an **existing deployment with the private backend already working**, plan
the final PoC configuration directly:

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-out=private-connectivity.tfplan"
# Review the saved plan, including gateway public access and any resource changes.
terraform apply "private-connectivity.tfplan"
```

For a **new deployment or a public-backend deployment**, establish networking
first with temporary model public access, then disable it:

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-var=models_public_network_access=Enabled" "-out=private-connectivity-stage1.tfplan"
# Review, then apply. Model public access is temporarily Enabled in this stage.
terraform apply "private-connectivity-stage1.tfplan"
# Verify approved private endpoints, private DNS, and gateway inference from the VNet.

terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-out=private-connectivity.tfplan"
# Review, then apply the model public-access Disabled / ACL Deny transition.
terraform apply "private-connectivity.tfplan"
```

Use an existing client connected to the VNet, or opt into the test VM by setting
`enable_private_test_client = true` and a real
`private_test_client_ssh_public_key` in your ignored inputs. The profile does not
enable or disable that VM; an already-enabled VM is preserved. See the test-client
instructions below for its no-public-IP design, Run Command probe and deallocation.

With the optional VM running, repeat the private probe after the final apply:

```powershell
.\scripts\Test-PrivateGateway.ps1
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" -detailed-exitcode
```

Require an `OK` response from every alias with model public access disabled,
and a final plan exit code of `0`. The probe obtains the gateway key through
managed identity without printing it. A passing pre-disablement probe is not
proof of private backend use. This probe does not independently verify negative
authentication or telemetry ingestion; those require separate runtime checks.
Do not reuse earlier failed private-only saved plans for this PoC.

## Optional private gateway/model proof

Set `enable_private_networking = true` to add a VNet, an outbound integration
subnet delegated to `Microsoft.Web/serverFarms`, separate endpoint/client
subnets, two private endpoints, and four private DNS zones. The gateway PE uses
group ID `Gateway`; the model account uses `account`. Gateway networking uses
the working `2025-09-01-preview` contract with `virtualNetworkType = "External"`.
Private Link alone does not provide outbound connectivity.

The default VNet is `10.247.0.0/16`. Set `private_network_address_prefix` to a
non-overlapping IPv4 /16 before first deployment if needed. Existing corporate
DNS, peering, VPN, forced tunnelling, and custom firewall rules are not configured.
Optional networking additionally requires `Microsoft.Network`; the optional
test VM requires `Microsoft.Compute` and regional VM quota.

Use staged, reviewed plans, with no resource replacements:

The profile above stops after stage 2 and intentionally keeps gateway public
access enabled. Stage 3 below is the separate, currently blocked private-only
ingress goal, not a prerequisite for the private-connectivity PoC.

1. Enable private networking, initially keeping `gateway_public_network_access`
   and `models_public_network_access` as `Enabled`. Verify endpoint approval and
   private DNS from inside the VNet.
2. Set `models_public_network_access = "Disabled"`, apply, and repeat gateway
   inference. Success with model public access disabled proves the backend path.
3. Set `gateway_public_network_access = "Disabled"`, apply, and repeat private
   inference. Also prove a previously working valid-key public request now fails.

**Observed preview result (October 18, 2026, Sweden Central):** private-client
DNS and inference passed for both configured aliases, including with model
public access disabled and its network ACL set to Deny. Disabling gateway public
access failed with `UpdateApiServiceFailed` through both Terraform's service
update and the dedicated CLI's public-access-only PATCH. The approved private
endpoint and outbound integration continued to work, but gateway public access
remained Enabled. A separate fresh minimal gateway in the same subscription and
region reproduced the error without outbound integration or model/backend
configuration, through both the service update and a public-access-only CLI
PATCH. Its approved private endpoint remained reachable; the temporary
reproduction resources were then deleted. This narrows the failure beyond the
original instance but does not establish a root cause or prove that the SKU
never supports private-only ingress. Do not declare private-only operation
until step 3 succeeds and the public negative test passes. No destructive
workaround or automatic re-enablement is included.

Optionally set `enable_private_test_client = true` and supply
`private_test_client_ssh_public_key` with an OpenSSH **public** key. The Ubuntu
`Standard_B2s_v2` VM has no public IP, denies all inbound traffic, and uses a
managed identity with a custom role granting only gateway API-key retrieval.
Its subnet explicitly enables default outbound internet for the VM agent/ARM:
this PoC client is not an air-gapped production design. Do not place secrets in
the public-key variable or in scripts.

From this Terraform directory, with the VM running:

```powershell
.\scripts\Test-PrivateGateway.ps1
```

The script reads non-secret Terraform outputs and uses VM Run Command to execute
the standard-library Python probe. It requires private DNS for both service
hosts and an `OK` inference response from every configured alias. The VM obtains
the runtime key in memory using managed identity; tokens and keys are not
printed or passed in Run Command parameters. A positive report before disabling
model public access is only a partial proof, not evidence of private backend use.

After testing, deallocate the VM to stop compute billing:

```powershell
$vmId = terraform output -raw private_test_vm_id
$subscriptionId = ($vmId -split '/')[2]
az vm deallocate --subscription $subscriptionId --ids $vmId
```

The managed disk, private endpoints, private DNS, and monitoring can still incur
charges. Start the VM again before rerunning the probe. Removing networking or
turning off its Terraform feature flag can destroy network resources and must
be reviewed separately. Re-enabling public access is an explicit security change,
not an automatic recovery step.

**Boundary:** this option does not privately network the hosted-agent account,
Storage, or ACR. It does not validate agent execution or promise an SLA.

## Preview schema limitations

AzAPI 2.13 does not bundle schemas for the preview connector gateway, telemetry
exporter, model provider/catalog, model alias, and runtime API key resources. Their blocks
set `schema_validation_enabled = false`; all other resource blocks retain the
provider's default schema validation. ARM still validates those resources when
they are provisioned. A successful offline check is **not** proof of preview
access, regional capacity, API acceptance, or runtime connectivity.

## Offline checks

```powershell
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

Tests use a mocked AzAPI provider with no Azure authentication or provisioning.
They check model/endpoint/token-limit propagation, independent gateway location,
identity-based backend configuration, opt-in developer roles, and invalid model
inputs. They do not call Azure or prove the hosted-agent application works.
The private-connectivity regression reads the committed JSON profile directly
and checks its mixed gateway-public/model-private posture, endpoint wiring,
managed-identity backend access, API-key resource and telemetry exporter.

## Runtime verification

After applying, follow the [gateway model test](../../cli/README.md#5-test-the-gateway)
using the gateway/resource-group outputs, provider `foundry`, and your configured
deployment names. The guide uses the optional AI Gateway CLI extension.
Expect an HTTP 200 response from every model and HTTP 401/403 when the runtime
key is absent or invalid. Model calls can incur inference charges; keep keys out
of terminal output, logs, and source control.

Confirm the six default RBAC assignments and the Foundry connections exist, and
check the gateway's Application Insights for the requests after allowing for
ingestion delay. Connection metadata alone does not prove that hosted agents can
access storage or pull an image. Finally, run `terraform plan -detailed-exitcode`;
exit code 0 means no drift, 2 means changes remain, and 1 means the plan failed.
Never override a policy-required storage network restriction to make this check
pass. Include the same explicit `-var-file` profile and overrides used for the
deployment when checking drift.

## References

- [Upstream Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra)
- [AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest/docs)
- [AI Gateway tier](https://aka.ms/aigateway/docs)
- [Model and tool management](https://learn.microsoft.com/azure/api-management/ai-gateway-manage-models-tools)
