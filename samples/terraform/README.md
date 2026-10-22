# AI Gateway and Foundry with Terraform

Manage an Azure AI Gateway that routes calls to Foundry models. This is standalone
Terraform for the [Foundry AI Gateway Python sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway), not an `azd` app.

> **Preview PoC, not production.** The AI Gateway preview has **no SLA**. Everything
> here is billable (model calls, Premium ACR, Storage, monitoring). Read the
> [limitations](docs/reference.md#limitations) before applying.

> **Existing deployments only.** This sample retains the legacy
> `Microsoft.ApiManagement/service` resource with SKU `AIGateway`. New gateways
> cannot be created with that SKU, and existing ones must migrate before
> **January 15, 2027**. This sample does not perform that migration.
> See [resource type and lifecycle](docs/reference.md#resource-type-and-lifecycle).

## Choose your networking path

The sample includes **both public and private connectivity**. The public path is
the Terraform default; the private profile adds private endpoints and routing.

| Path | Private endpoints | Gateway public access | Model public access |
| --- | --- | --- | --- |
| [Private connectivity](#private-connectivity-path) | Gateway and model account | **Enabled** | **Disabled** after staging |
| [Public endpoints](#public-endpoint-path) | None | Enabled | Enabled |

**Private connectivity is not private-only gateway access.** The private profile
provides a private route to the gateway and models, but the gateway's public
endpoint remains enabled because of the [observed public-disable blocker](docs/reference.md#known-blocker-private-only-gateway-ingress).

**Already using the private profile?** Follow [existing private deployments](docs/private-connectivity.md#existing-private-deployments).
Keep the profile on every plan, including drift checks. Do not follow the public
path or repeat the temporary-public staging step for an already-private backend.

## Before you start

**Check these first:**

- [ ] Terraform 1.11+ (below 2.0) and Azure CLI installed
- [ ] Existing legacy AIGateway deployment and subscription access to Foundry hosted agents in your regions
- [ ] Permission to create resources and role assignments (for example, Contributor plus Role Based Access Control Administrator)
- [ ] Providers registered: `Microsoft.ApiManagement`, `Microsoft.Web`, `Microsoft.CognitiveServices`, `Microsoft.Storage`, `Microsoft.ContainerRegistry`, `Microsoft.OperationalInsights`, `Microsoft.Insights` (this sample does not register them for you)
- [ ] Quota for the model and SKU in your region

**Decide before you start:**

- **Public endpoints OK?** If your policy prohibits public gateway or model endpoints, even temporarily, do not run this sample unchanged.
- **Need private hosted-agent execution?** Set it when the Foundry account is created. This sample does not configure it, and you cannot add it to an existing account later.
- **Need private-only gateway ingress?** Not achievable with this sample. See the [known blocker](docs/reference.md#known-blocker-private-only-gateway-ingress).

## What gets deployed

| Component | Purpose |
| --- | --- |
| **AI Gateway** | Front door: checks the runtime API key, applies token limits, routes to a model alias, records telemetry. It does not run models. |
| **Foundry model account** | Runs the models. The gateway authenticates with its managed identity, not an API key. |
| **Foundry hosted-agent account and project** | Prepared for a *later* agent app: Storage, Premium Container Registry, roles and connections. **No agent, image or running container is deployed.** |
| **Private network (private path)** | Gateway and model private endpoints, DNS, and gateway outbound VNet integration. See [private connectivity](docs/private-connectivity.md). |
| **Optional private test VM** | Probe client for the private path. It is not required if you already have a suitable private client. |

Both paths manage all three core components. Hosted-agent infrastructure is
included even if you only test model calls.

**Authentication in both paths** (independent of public or private routing):

```text
Client --(runtime API key)--> AI Gateway --(managed identity)--> Foundry model account
```

A **model alias** (for example, `gpt-mini`) is the name clients send. It does not have to match the underlying model name (for example, `gpt-4.1-mini`).

## Shared setup

Run from `samples/terraform` for either networking path. Use the existing
deployment's input file and Terraform state/backend. Do not start with an empty
state for resources already managed by this sample.

**1. Sign in:**

```powershell
az login
```

**2. Review the existing `terraform.tfvars`:**

| Setting | What to set |
| --- | --- |
| `subscription_id` | Where resources are created |
| `environment_name` | Existing deployment label; changing it changes resource names |
| `location`, `gateway_location` | Foundry and gateway regions (independent of each other) |
| `publisher_email` | Gateway publisher contact |
| `model_deployments` | Model versions, capacity and token limits. Keys (`gpt-mini`, `gpt-full`) become client-facing aliases. |
| `storage_public_network_access` | `Disabled` only if your policy requires it |

This file is git-ignored. Do not overwrite it with
[terraform.tfvars.example](terraform.tfvars.example), which documents the input
shape only. Optional settings are in the [input reference](docs/reference.md#inputs).

**3. Initialize and check:**

```powershell
az account set --subscription "<subscription-id>"
terraform init
terraform fmt -check -recursive
terraform validate
```

Continue with **one** of the networking paths below.

## Private connectivity path

Use [profiles/private-connectivity.tfvars.json](profiles/private-connectivity.tfvars.json)
for private client-to-gateway and gateway-to-model traffic:

```text
Private client -> gateway private endpoint -> gateway outbound VNet integration -> model private endpoint
```

Follow the [private-connectivity guide](docs/private-connectivity.md) for the
staged plan/apply, private probe, and VM lifecycle. The gateway public endpoint
stays enabled; model public access is disabled in the final profile.

**Do not run the public-path plan below for this configuration.** Omitting the
private profile can plan removal of private networking or re-enable model public
access, depending on your other inputs.

## Public endpoint path

Use this path only for a deployment intentionally configured without private
networking. It is not a prerequisite for the private path.

**1. Plan and review:**

```powershell
terraform plan "-out=deployment.tfplan"
```

Stop if planning fails. Review the plan for public access, resource creation and
cost. Do not apply unexpected changes.

**2. Apply the reviewed plan:**

```powershell
terraform apply "deployment.tfplan"
```

**3. Test every alias:**

```powershell
.\scripts\Test-ModelAliases.ps1
```

Each alias should print a short reply, for example `gpt-mini: Hello!`.
This check uses your machine and public endpoints. It does **not** prove private routing.
The example calls every configured alias and assumes chat-completions models,
such as the two models in `terraform.tfvars.example`. For other model types,
use their supported API and request body instead.

**Done when:** every alias returns a response and `terraform plan -detailed-exitcode` exits `0`.

## Additional runtime checks

For either path, also verify:

- Missing or invalid API keys get HTTP `401/403`. A successful call does not prove this.
- The six default RBAC assignments and Foundry connections exist.
- Requests appear in the gateway's Application Insights after ingestion delay.

## Going further

- [Reference](docs/reference.md): file guide, all inputs, outputs, networking, state and security, offline tests, limitations
- [Cost and cleanup](docs/reference.md#cost-and-cleanup)
