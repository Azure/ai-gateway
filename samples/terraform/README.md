# AI Gateway and Foundry infrastructure with Terraform

**Use this sample to deploy an AI Gateway and call Foundry models through it.**
It also prepares a separate Foundry project for a hosted-agent application, but
does not deploy or run that application.

This is standalone Terraform infrastructure for the
[Foundry AI Gateway Python sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway),
not an `azd` application.

**Read in this order:** [understand the components](#what-is-provisioned),
[choose a path](#choose-your-deployment), complete the
[shared setup](#configure-and-provision), then follow **only Path A or Path B**.
The [technical reference](#technical-reference) is for looking up details,
not a second deployment walkthrough.

## What is provisioned

### What each component is for

| Component | Its job | What you get from this sample |
| --- | --- | --- |
| **AI Gateway** | The front door for model calls: authenticates clients, applies token limits, routes requests and records telemetry. It does not run the model itself. | A dedicated **AIGateway** preview SKU, model registrations/aliases, a runtime API key resource and monitoring. |
| **Foundry model account** | Runs the deployed models that answer requests forwarded by the gateway. | A separate AI Services account with the model versions and capacity you choose. The gateway uses its managed identity to access it, not a backend API key. |
| **Foundry hosted-agent account and project** | The foundation for a later application that runs an agent. Storage holds project artifacts; Container Registry holds its container image. | Account/project, Storage, Premium Container Registry, access roles, connections and monitoring. **No agent image, definition or running container.** |
| **Optional private network and test VM** | Adds and verifies a private route between a client, the gateway and the models. | Gateway/model private endpoints, private DNS, gateway outbound VNet integration and an optional VM that runs a probe. **Does not privately network the hosted-agent component.** |

**Both deployment paths create all three core components.** Choosing the private
profile changes networking; it does not select a smaller gateway-only deployment.
Hosted-agent infrastructure is provisioned even if you only test model calls.

### How a model request flows

```text
Your application or test client
    |
    | Runtime API key: authenticates the client to the gateway
    v
AI Gateway: validates the key, applies token limits, selects a model alias
    |
    | Managed identity: authenticates the gateway to the model account
    v
Foundry model account: runs the selected model and returns the answer
```

A **model alias** is the name your client sends, such as `gpt-mini`; it is not
necessarily the underlying model name, such as `gpt-4.1-mini`.
The hosted-agent project is not needed to execute this test request. Deploying
an actual agent, building/pushing its image, configuring GitHub MCP credentials
and setting a daily-digest schedule are separate application steps in the
end-to-end sample. This Terraform configuration does not replace its `azd` hooks.

## Choose your deployment

| | Path A: public-endpoint sample | Path B: private-connectivity PoC |
| --- | --- | --- |
| **Use it to** | Make a first authenticated model call through the gateway. | Demonstrate private client-to-gateway and gateway-to-model connectivity. |
| **Client location** | Your local machine can call the public gateway. | A client inside or connected to the VNet; the included test VM is the walkthrough's example. |
| **Gateway public access** | Enabled. | **Still enabled**; valid-key public calls can still work. |
| **Model public access** | Enabled. | Disabled after a temporary-public setup stage. |
| **Additional resources** | No sample VNet or test VM by default. | VNet, private endpoints/DNS and optional billable test VM. |
| **Instructions after shared setup** | [Path A](#path-a-public-endpoint-sample) | [Path B](#private-connectivity-poc-profile) |
| **Completion means** | Every configured alias returns a model response. | Every alias works from the VNet with model public access disabled; no pending Terraform changes. |

### Stop and check these constraints first

**Preview PoC, not a production security baseline.** Review the full
[disclaimer and official Microsoft Learn sources](#disclaimer-and-current-limitations)
before applying. In particular:

- **No public gateway ingress allowed? Neither path meets that requirement.**
  Gateway public-access disablement failed in the tested environment;
  [private-only ingress remains blocked](#known-blocker-private-only-gateway-ingress).
- **Need private hosted-agent execution? Decide before creating the account.**
  Microsoft requires hosted-agent VNet injection at Foundry account creation;
  this sample does not configure it. Adding private endpoints later is not a
  substitute.
- **Public model endpoints prohibited, even temporarily?** Do not run Path A or
  Path B's staging unchanged. Review a policy-compliant deployment separately.

The gateway preview has **no SLA**. Both paths create billable resources;
model calls, Premium ACR, Storage and monitoring can incur charges.

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
Path B additionally requires `Microsoft.Network`; the test VM requires
`Microsoft.Compute`, regional VM quota and permission to use VM Run Command.

## Configure and provision

**Shared setup for both paths.** These steps prepare your inputs and Terraform;
they do not deploy resources yet. All later commands run from this same directory.

### Prepare your personal input file

From the repository root, sign in and copy the example **only if you do not
already have `terraform.tfvars`**:

```powershell
Set-Location .\samples\terraform
az login
# Fresh checkout only; do not overwrite existing inputs.
Copy-Item terraform.tfvars.example terraform.tfvars
```

For a fresh checkout, copy the example once. If you already have
`terraform.tfvars`, edit it instead of overwriting it. Before continuing, open
the file and set:

| Set in `terraform.tfvars` | Why it matters |
| --- | --- |
| `subscription_id` | Determines where resources are created. |
| `environment_name` | Distinguishes this deployment from another environment. |
| `location` and `gateway_location` | Choose supported Foundry/model and gateway regions respectively. |
| `publisher_email` | Gateway publisher contact. |
| `model_deployments` | Choose model versions, deployment capacity and token limits available to your subscription. The example's `gpt-mini` and `gpt-full` keys become the client-facing aliases. |
| `storage_public_network_access`, if policy requires it | Use `Disabled` when required by policy; private hosted-agent storage connectivity is not supplied here. |

Keep this file local: it is ignored by Git. See the
[input reference](#inputs) for optional fields. Review
[state and security](#state-and-security) before applying; state and saved plans
can contain sensitive data.

### Initialize Terraform

```powershell
az account set --subscription "<subscription-id-from-terraform.tfvars>"
terraform init
terraform fmt -check -recursive
terraform validate
```

Stop if a command fails. Choose **one** path below; do not run both sets of
plan/apply commands in sequence. This creates new infrastructure, not an
automatic import of existing Bicep resources. Names depend on subscription,
environment name and Foundry region; changing those inputs can replace resources.

## Path A: public-endpoint sample

**Purpose:** get a first model response without setting up private networking.
Use this only when your policies permit public gateway and model endpoints.
On a fresh checkout, the example inputs use this posture; do not reuse unrelated
private-network overrides.

```powershell
terraform plan "-out=deployment.tfplan"
```

Review the plan, including public access, resource creation and costs. Then apply
that reviewed plan:

```powershell
terraform apply "deployment.tfplan"
```

**Next:** run [Test a model through the gateway](#test-a-model-through-the-gateway),
then [check telemetry and deployment consistency](#check-telemetry-and-deployment-consistency).
You are done with Path A when every alias returns a response and the final
plan has no pending changes. This does not deploy an agent application.

## Private-connectivity PoC profile

**Path B. Purpose:** prove the following private route, using the same dedicated
AIGateway SKU and core infrastructure as Path A:

```text
Private client -> gateway private endpoint -> private model endpoint
```

| Setting | Profile value |
| --- | --- |
| `enable_private_networking` | `true` |
| `gateway_public_network_access` | `Enabled` |
| `models_public_network_access` | `Disabled` |

Select [profiles/private-connectivity.tfvars.json](profiles/private-connectivity.tfvars.json)
explicitly for this path. It adds gateway/model private endpoints, DNS and
gateway outbound VNet integration to the same deployment, not a second gateway.
Gateway identity-based backend access, API-key authentication and telemetry
remain in place. Model local authentication is disabled and, in the final
configuration, its network ACL becomes Deny.

**Not private-only ingress:** clients can use the gateway private endpoint,
but the public gateway endpoint remains reachable with valid credentials.
The profile does not claim to fix the public-disablement failure documented
below. Hosted-agent networking is unchanged and agent execution is not proven.

### B1. Choose the client that will prove private connectivity

Your laptop is not automatically connected to the new VNet. The steps below use
the optional test VM so no VPN or inbound SSH is needed. Before the first plan,
add these inputs to your ignored `terraform.tfvars`, replacing the key
placeholder with a real OpenSSH ed25519 or RSA **public** key:

```hcl
enable_private_test_client         = true
private_test_client_ssh_public_key = "ssh-ed25519 <your-public-key>"
```

The key is required to provision the VM; the probe uses Azure VM Run Command,
not SSH. Never paste a private key or password. The VM is billable, has no
public IP and denies inbound traffic. See [networking reference](#networking-reference)
for its outbound-access design and required network settings.

If you already have a client connected to the VNet, you can omit the VM.
Replace the VM-probe steps below with equivalent private DNS and inference
checks from that client; `Test-PrivateGateway.ps1` specifically requires the VM.

### B2. Create networking with the model temporarily public

For a **new deployment or a public-backend deployment**, first make the private
route available. This stage is not the final security posture.

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-var=models_public_network_access=Enabled" "-out=private-connectivity-stage1.tfplan"
```

Review the plan: both gateway and model public access are temporarily enabled,
and networking plus the selected test VM are created. Do not apply unexpected
replacements. Then:

```powershell
terraform apply "private-connectivity-stage1.tfplan"
```

### B3. Check the private route before disabling model public access

With the test VM running:

```powershell
.\scripts\Test-PrivateGateway.ps1
```

The script runs inside the VM through Run Command. It checks that the gateway
and model hostnames resolve into the private endpoint subnet and every alias
answers `OK`. The VM retrieves the gateway key using managed identity; no key
is printed or passed as a Run Command argument.

**Stop if the probe fails.** Check endpoint approval, private DNS, permissions
and outbound integration before continuing. A pass here is only an initial
connectivity check: model public access is still enabled.

### B4. Disable model public access

Plan again **without** the temporary `Enabled` override:

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-out=private-connectivity.tfplan"
```

Review the transition: model public access becomes `Disabled` / ACL Deny;
gateway public access stays `Enabled`. Then:

```powershell
terraform apply "private-connectivity.tfplan"
```

### B5. Prove the final private path

```powershell
.\scripts\Test-PrivateGateway.ps1
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" -detailed-exitcode
```

**Path B is complete only when** the probe reports `"passed": true` with `OK`
for every alias while model public access is disabled, and the final plan exits
with code `0`. This proves the gateway/model private path, not private-only
gateway ingress or hosted-agent execution.

Also perform the [authentication and telemetry checks](#check-telemetry-and-deployment-consistency):
the private probe does not independently test invalid keys or telemetry ingestion.

### B6. Stop test VM compute billing

After testing, **if you created the optional VM** (otherwise skip this step):

```powershell
$vmId = terraform output -raw private_test_vm_id
$subscriptionId = ($vmId -split '/')[2]
az vm deallocate --subscription $subscriptionId --ids $vmId
```

Disks, private endpoints, DNS, model deployments and monitoring can still incur
charges. To use the VM again:

```powershell
az vm start --subscription $subscriptionId --ids $vmId
```

### Existing deployments and profile precedence

If your deployment already has a working private backend with model public
access disabled, you can start at B4, review the final profile plan, then run B5.
Keep your existing client choice; the profile does not turn the test VM on or off.

The profile is not auto-loaded: include `-var-file` on every plan for Path B,
including drift checks. Its three values override `terraform.tfvars` and
`*.auto.tfvars`, even an old private-only override. Later `-var` or `-var-file`
arguments can override it again. Keep personal settings in the ignored inputs,
not the committed profile. Do not apply stale private-only plans or re-enable
public access as an automatic recovery step.

## Runtime verification

### Which check proves what?

| Check | Where it runs | What it proves |
| --- | --- | --- |
| Model request below | Your current machine, against the gateway endpoint. | Authentication and a successful model response. **Not private routing.** Use for Path A or an additional Path B smoke check. |
| [Path B private probe](#b3-check-the-private-route-before-disabling-model-public-access) | Inside the optional VM via Azure Run Command. | Private DNS and inference. Repeat after disabling model public access to establish private backend use. |
| `terraform plan -detailed-exitcode` | Your Terraform working directory. | Configuration consistency, not successful runtime calls. |
| [Offline checks](#offline-checks) | Locally with a mocked provider. | Configuration assertions, not Azure access or runtime behavior. |

### Test a model through the gateway

Run this in PowerShell from `samples\terraform` after a successful apply, while
signed in to Azure. It uses Terraform outputs and Azure CLI; the optional AI
Gateway CLI extension is **not required**. Your signed-in identity needs
permission to retrieve the gateway API key
(`Microsoft.ApiManagement/service/apiKeys/listSecrets/action`).

The example calls every configured alias and assumes chat-completions models,
such as the two models in `terraform.tfvars.example`. For other model types,
use their supported API and request body instead. Model calls incur inference
charges. Do not enable CLI debug output, PowerShell tracing or session recording
while retrieving or using keys.

```powershell
$outputJson = terraform output -json
if ($LASTEXITCODE -ne 0) { throw "Unable to read Terraform outputs." }
$outputs = $outputJson | ConvertFrom-Json
$gatewayUrl = ([string]$outputs.gateway_endpoint.value).TrimEnd('/')
$keyId = $outputs.gateway_api_key_id.value
$modelNames = @($outputs.model_deployment_ids.value.PSObject.Properties.Name)
if (!$gatewayUrl -or !$keyId -or $modelNames.Count -eq 0) {
    throw "Gateway endpoint, API key resource ID, or model aliases are missing."
}

$apiKey = $null
$headers = $null
try {
    $apiKey = az rest --method post `
        --url "https://management.azure.com${keyId}/listSecrets?api-version=2025-09-01-preview" `
        --query primaryKey --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($apiKey)) {
        throw "Unable to retrieve the gateway key; check your Azure identity and permissions."
    }
    $headers = @{ "Api-Key" = $apiKey }
    foreach ($model in $modelNames) {
        $body = @{
            model = $model
            messages = @(@{ role = "user"; content = "Say hello in one short sentence." })
        } | ConvertTo-Json -Depth 5
        $reply = Invoke-RestMethod -Method Post `
            -Uri "$gatewayUrl/default/models/openai/v1/chat/completions" `
            -Headers $headers -ContentType "application/json" -Body $body -ErrorAction Stop
        if (!$reply.choices -or !$reply.choices[0].message.content) {
            throw "No chat-completion text returned for model alias '$model'."
        }
        "{0}: {1}" -f $model, $reply.choices[0].message.content
    }
}
finally {
    $headers = $null
    $apiKey = $null
}
```

Expect a short reply prefixed by each alias, for example `gpt-mini: Hello!`.
The key is held in memory and cleared from the example's variables even if a
request fails; it is not printed or written to a file. Stop on errors rather
than disabling authentication or relaxing network policies. A `401/403` can
indicate authentication, authorization or network restrictions; a `429` can
indicate token limits or capacity. Inspect the service error before retrying.

**This direct request does not prove private routing.** With the PoC profile,
a public client can still reach the gateway. Use the
[private test-client probe](#b3-check-the-private-route-before-disabling-model-public-access) from the
VNet to verify private DNS and inference with model public access disabled.

For CLI-based alternatives, follow the
[gateway model test](../../cli/README.md#5-test-the-gateway), using provider
`foundry` and your configured deployment names.

### Check telemetry and deployment consistency

For either path, separately verify that missing or invalid runtime keys receive
HTTP `401/403`; a successful authenticated call does not test that protection.

Confirm the six default RBAC assignments and the Foundry connections exist, and
check the gateway's Application Insights for the requests after allowing for
ingestion delay. Connection metadata alone does not prove that hosted agents can
access storage or pull an image. Finally, run `terraform plan -detailed-exitcode`;
exit code 0 means no drift, 2 means changes remain, and 1 means the plan failed.
Never override a policy-required storage network restriction to make this check
pass. Include the same explicit `-var-file` profile and overrides used for the
deployment when checking drift.

## Technical reference

**Look up details here as needed.** You do not need to execute another deployment
path or modify every file below to use the sample.

### File guide

| File | What it controls | When you need it |
| --- | --- | --- |
| [terraform.tfvars.example](terraform.tfvars.example) | Template for subscription, region, model and publisher inputs. | Copy once to your ignored `terraform.tfvars`; edit your copy, not the template. |
| [profiles/private-connectivity.tfvars.json](profiles/private-connectivity.tfvars.json) | Three networking settings for Path B. No subscription or credentials. | Select explicitly on Path B plans; not needed for Path A. |
| [variables.tf](variables.tf) / [outputs.tf](outputs.tf) | Supported inputs, validation and exported resource information. | Look up an optional setting or find an endpoint/resource ID. |
| [ai-gateway.tf](ai-gateway.tf) | AIGateway service, connector gateway, provider, catalog, aliases, runtime key resource and telemetry exporter. | Understand gateway routing and policies. |
| [foundry-models.tf](foundry-models.tf) | Model account and versioned deployments. | Understand backend provisioning; choose models through inputs. |
| [foundry-agents.tf](foundry-agents.tf) | Agent account/project, Storage, Premium ACR and connections. | Understand what is prepared for the separate agent application. |
| [main.tf](main.tf) / [rbac.tf](rbac.tf) | Naming, three resource groups, monitoring and access roles. | Understand shared infrastructure and identity permissions. |
| [private-network.tf](private-network.tf) / [private-test-client.tf](private-test-client.tf) | Optional VNet, private endpoints/DNS, gateway integration and probe VM. | Path B networking implementation. |
| [scripts\Test-PrivateGateway.ps1](scripts/Test-PrivateGateway.ps1) / [Python probe](scripts/private-path-probe.py) | Read non-secret outputs and run DNS/inference checks inside the VM. | Execute Path B's probe with the PowerShell wrapper; it sends the Python code to the VM. |
| [tests](tests) | Mocked Terraform assertions and Python probe unit tests. | Develop or check the sample offline; no live deployment proof. |
| [versions.tf](versions.tf) / [.terraform.lock.hcl](.terraform.lock.hcl) | Provider requirements and locked provider checksums. | Reproduce dependency selection; keep the lock file committed. |

### Inputs

The [shared setup](#configure-and-provision) covers the minimum values to edit.
These optional settings refine that configuration:

| Input | Purpose and default |
| --- | --- |
| `environment_name` | Naming/tagging label; defaults to `aigateway`. |
| `storage_public_network_access` | `Enabled` by default; use `Disabled` when policy requires it. No private storage path is created here. |
| `developer_principal_id` | Optional Entra object ID for developer access; empty means no developer role assignments. |
| `developer_principal_type` | `User`, `Group` or `ServicePrincipal`; defaults to `User`. |
| `publisher_name`, `project_display_name`, `project_description`, `tags` | Display metadata and additional tags. |
| `private_network_address_prefix` | Path B VNet IPv4 /16; defaults to `10.247.0.0/16`. Choose a non-overlapping range before first deployment. |
| `enable_private_test_client` | Adds the Path B VM; defaults to `false`. Requires private networking. |
| `private_test_client_ssh_public_key` | Real OpenSSH public key required when creating the VM. |
| `private_test_client_vm_size` | Defaults to `Standard_B2s_v2`; check availability and quota. |

Each `model_deployments` entry requires `model_name`, `model_version`,
`capacity` and `token_limit`. `capacity` is a model deployment SKU-specific
quota unit; `token_limit` is the gateway's per-identity tokens-per-minute limit.
They are independent, not a universal conversion. Optional model fields are
`model_format`, `sku_name`, `api_format`, `endpoints` and `description`; match
API format/endpoints to the model's capabilities. See [variables.tf](variables.tf)
for complete types, defaults and validation.

### Outputs and credentials

| Output | Use it for |
| --- | --- |
| `gateway_endpoint` | Base URL for runtime calls through the gateway. |
| `gateway_api_key_id` | ARM ID used to retrieve the runtime key through an approved process. **Not the key value.** |
| `model_deployment_ids` | Model IDs keyed by the client-facing aliases. |
| `project_endpoint`, `project_id` | Separate hosted-agent application setup. Not a gateway model-call URL. |
| `container_registry_endpoint`, `storage_account_name` | Image publishing and project artifact setup for that application. |
| `resource_groups`, `gateway_id`, `foundry_models_id`, `application_insights_ids` | Resource management and telemetry lookup. |
| `private_endpoint_ids`, `private_test_vm_id`, `private_probe_configuration` | Path B resource lookup and VM probe inputs. VM outputs are only available when the test client is enabled. |

`terraform output` does not export runtime key values or telemetry connection
strings. Backend calls, storage and image pulls use managed identities. Retrieve
runtime key values through your approved secret-management process; do not put
them in `.tfvars`, terminal output or source control.

### Networking reference

Path B adds a VNet, an outbound integration subnet delegated to
`Microsoft.Web/serverFarms`, separate endpoint/client subnets, two private
endpoints and four private DNS zones. Gateway PE group ID is `Gateway`; model
PE group ID is `account`. The sample's tested gateway contract is
`2025-09-01-preview` with `virtualNetworkType = "External"`. Inbound Private
Link and outbound integration solve different problems; one does not replace
the other.

The optional Ubuntu VM has no public IP, denies inbound traffic and has only a
narrow custom role for gateway API-key retrieval. Its subnet explicitly allows
default outbound internet for VM agent/ARM operations; it is not air-gapped.
The probe reads non-secret outputs and uses standard-library Python inside the
VM; your local machine does not need a private route to run the wrapper.

Existing corporate DNS, peering, VPN, forced tunnelling and custom firewall
rules are not configured. Review same-region outbound VNet requirements,
dedicated subnets, DNS and NSG dependencies in the
[official gateway networking guide](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking).
Removing networking or disabling its feature flag can destroy network resources;
review those changes separately. This network does not isolate the agent
account, Storage or ACR.

### State and security

- This demonstration uses **local state**. State and saved plans can contain
  sensitive responses, including telemetry connection strings. Restrict access
  and do not commit them. `.gitignore` excludes state, plans, provider downloads
  and user `.tfvars`; the only `.tfvars.json` exception is the non-secret profile.
- Before shared or production use, configure an access-controlled remote backend
  with encryption/locking, such as Azure Blob Storage with Entra authentication;
  migrate local state using `terraform init -migrate-state`.
- Storage forbids anonymous blobs and shared keys. ACR admin credentials and
  Foundry local authentication are disabled. Gateway telemetry payload capture
  is disabled.
- Preserve policy-required storage restrictions. Gateway/model testing can work
  independently, but private hosted-agent storage connectivity remains unverified
  until configured separately.
- Project roles mirror the upstream Bicep, including Cognitive Services
  Contributor. Optional developer access also grants Storage Blob Data Contributor.
  Enable it deliberately and review least privilege.

### Implementation background and preview schemas

The configuration follows the upstream
[Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra)
and [model-registration fix](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/commit/03fcd3788aea06cf6000af19890f8164303348d5).
AzAPI expresses the preview ARM resources directly. Model operations are
serialized per account using resource locks. The automatically created gateway
`default` workspace is referenced, not created again. Each catalog entry needs
a workspace alias for runtime routing; token policies use `["identity"]`
instead of the older scalar `"Identity"` counter key.

AzAPI 2.13 lacks bundled schemas for the preview connector gateway, telemetry
exporter, model provider/catalog, alias and runtime API key resources. Those
blocks set `schema_validation_enabled = false`; other blocks retain default
schema validation. ARM still validates the resources at provisioning time.
Offline success does not establish preview access, capacity or API acceptance.

### Offline checks

For configuration checks without provisioning Azure resources:

```powershell
terraform init -backend=false
terraform fmt -check -recursive
terraform validate
terraform test
```

The Terraform tests mock AzAPI and require no Azure authentication. They check
model/endpoint/token-limit propagation, independent gateway location,
identity-based backend configuration, opt-in developer roles and invalid inputs.
The private regression reads the committed JSON profile and asserts its mixed
gateway-public/model-private posture, endpoint wiring, backend identity,
API-key resource and telemetry exporter. These are not runtime tests.

## Disclaimer and current limitations

**Preview PoC, not a production or private-only reference architecture.**
Documentation checked **October 19, 2026**. The following separates
Microsoft-documented constraints from local test findings; revisit the official
sources before deploying because preview features and restrictions can change.

### Microsoft-documented constraints

**AI Gateway preview:** best-effort availability with **no SLA**; APIs, limits,
regions and pricing can change. Current documented gateway regions are East US 2
and Sweden Central, with access/capacity varying by subscription. Connected
services remain billable. See [AI Gateway overview and FAQ](https://learn.microsoft.com/azure/api-management/ai-gateway-overview).

**Hosted-agent isolation is a creation-time decision:** hosted-agent VNet
injection must be included when the Foundry account is first created; it cannot
be added to an existing account. This sample does not configure it. If private
hosted-agent execution is required, choose a supported network-secured Foundry
deployment before creating the account. See
[Foundry Agent Service networking limitations](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations).

**This is not a general ban on adding private endpoints later.** Microsoft
documents adding an inbound private endpoint to an existing gateway and configuring
outbound integration separately. Private endpoints alone do not provide gateway
or hosted-agent outbound access. See
[AI Gateway private networking](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking).

**Private hosted-agent image pulls:** current guidance supports private ACR for
Foundry projects created after June 25, 2026; older projects require public ACR
reachability. This does not remove the account-creation requirement for injection.
The sample leaves ACR public and does not prove agent execution. See
[Foundry networking limitations](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations).

### Known blocker: private-only gateway ingress

**Observed test finding, not a deployment step or a universal SKU limitation.**
Microsoft [documents disabling public access after private connectivity is
verified](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking#inbound-private-link).
In our **October 18, 2026, Sweden Central** tests:

- Both configured aliases passed private DNS/inference checks with model public
  access disabled and its network ACL set to Deny.
- Disabling gateway public access failed with `UpdateApiServiceFailed` through
  Terraform's service update and the dedicated CLI's public-access-only PATCH.
  Private connectivity kept working, but gateway public access stayed enabled.
- A separate minimal gateway in the same subscription/region reproduced the
  failure without outbound integration or model/backend configuration, using
  both update methods. Its private endpoint remained reachable; temporary
  reproduction resources were deleted.

Root cause remains unknown. Do not set gateway public access to `Disabled` as
part of this working PoC or present it as private-only. A future private-only
implementation must show the gateway reports `Disabled`, every alias still
works privately, a previously working valid-key public call receives a
network-access rejection (not just an authentication error), and the intended
private-only plan has no pending changes. No destructive workaround or automatic
public-access recovery is included.

## References

- [Upstream Bicep infrastructure](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway/tree/c572db847e4bff5278bc5f8630c2acb4b6991119/infra)
- [AzAPI provider](https://registry.terraform.io/providers/Azure/azapi/latest/docs)
- [AI Gateway tier](https://aka.ms/aigateway/docs)
- [AI Gateway overview, preview availability and SLA](https://learn.microsoft.com/azure/api-management/ai-gateway-overview)
- [Configure private networking for AI Gateway](https://learn.microsoft.com/azure/api-management/ai-gateway-configure-private-networking)
- [Foundry Agent Service private networking and limitations](https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks#limitations)
- [Model and tool management](https://learn.microsoft.com/azure/api-management/ai-gateway-manage-models-tools)
