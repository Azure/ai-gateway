# AI Gateway and Foundry with Terraform

Deploy an Azure AI Gateway that routes calls to Foundry models. This is standalone
Terraform for the [Foundry AI Gateway Python sample](https://github.com/Azure-Samples/simple-foundry-hosted-agent-python-aigateway), not an `azd` app.

> **Preview PoC, not production.** The AI Gateway preview has **no SLA**. Everything
> here is billable (model calls, Premium ACR, Storage, monitoring). Read the
> [limitations](docs/reference.md#limitations) before applying.

## Before you start

**Check these first:**

- [ ] Terraform 1.11+ (below 2.0) and Azure CLI installed
- [ ] Subscription enabled for the **preview AIGateway tier** and Foundry hosted agents in your regions
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
| **Optional private network and test VM** | Private endpoints and DNS for the gateway and models, plus a probe VM. See [private connectivity](docs/private-connectivity.md). |

Both paths create all three core components. Hosted-agent infrastructure is
created even if you only test model calls.

**Request flow:**

```text
Client --(runtime API key)--> AI Gateway --(managed identity)--> Foundry model account
```

A **model alias** (for example, `gpt-mini`) is the name clients send. It does not have to match the underlying model name (for example, `gpt-4.1-mini`).

## Quick start (public endpoints)

Run from `samples/terraform`.

**1. Sign in and create your input file** (only on a fresh checkout; never overwrite an existing `terraform.tfvars`):

```powershell
az login
Copy-Item terraform.tfvars.example terraform.tfvars
```

**2. Edit `terraform.tfvars`:**

| Setting | What to set |
| --- | --- |
| `subscription_id` | Where resources are created |
| `environment_name` | Distinguishes this deployment |
| `location`, `gateway_location` | Foundry and gateway regions (independent of each other) |
| `publisher_email` | Gateway publisher contact |
| `model_deployments` | Model versions, capacity and token limits. Keys (`gpt-mini`, `gpt-full`) become client-facing aliases. |
| `storage_public_network_access` | `Disabled` only if your policy requires it |

This file is git-ignored. Optional settings are in the [input reference](docs/reference.md#inputs).

**3. Initialize and check:**

```powershell
az account set --subscription "<subscription-id>"
terraform init
terraform fmt -check -recursive
terraform validate
```

**4. Plan and review:**

```powershell
terraform plan "-out=deployment.tfplan"
```

Stop if planning fails. Review the plan for public access, resource creation and
cost. Do not apply unexpected changes.

**5. Apply the reviewed plan:**

```powershell
terraform apply "deployment.tfplan"
```

**6. Test every alias:**

```powershell
.\scripts\Test-ModelAliases.ps1
```

Each alias should print a short reply, for example `gpt-mini: Hello!`.
This check uses your machine and public endpoints. It does **not** prove private routing.
The example calls every configured alias and assumes chat-completions models,
such as the two models in `terraform.tfvars.example`. For other model types,
use their supported API and request body instead.

**Done when:** every alias returns a response and `terraform plan -detailed-exitcode` exits `0`.

**Also verify:**

- Missing or invalid API keys get HTTP `401/403`. A successful call does not prove this.
- The six default RBAC assignments and Foundry connections exist.
- Requests appear in the gateway's Application Insights after ingestion delay.

## Private connectivity (optional)

Use this only if you need private client-to-gateway and gateway-to-model traffic.
Steps are in [docs/private-connectivity.md](docs/private-connectivity.md).

## Going further

- [Reference](docs/reference.md): file guide, all inputs, outputs, networking, state and security, offline tests, limitations
- [Cost and cleanup](docs/reference.md#cost-and-cleanup)
