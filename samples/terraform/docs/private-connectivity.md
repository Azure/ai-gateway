# Private connectivity path

This is the private alternative to the [public endpoint path](../README.md#public-endpoint-path),
not an extra step after its public plan/apply. It applies to the existing legacy
gateway resource retained by this sample; see [resource type and lifecycle](reference.md#resource-type-and-lifecycle).

**Goal:** prove this route works privately:

```text
Private client -> gateway private endpoint -> private model endpoint
```

**Settings used by this profile:**

| Setting | Value |
| --- | --- |
| `enable_private_networking` | `true` |
| `gateway_public_network_access` | `Enabled` (stays on; public calls with a valid key still work) |
| `models_public_network_access` | `Disabled` after step 4 |

Always pass the profile on every plan, including drift checks:
`-var-file=profiles\private-connectivity.tfvars.json`. It overrides `terraform.tfvars`.

> **Pending: private-only gateway ingress.** The observed public-disable failure
> is under investigation with the product group. Until a fix is verified, the
> profile keeps gateway public access enabled and is **not private-only**. See the
> [status and observed behavior](reference.md#known-blocker-private-only-gateway-ingress).
>
> Hosted-agent networking and proof of agent execution remain outside this profile.

**Already have a working private deployment?** Go to
[existing private deployments](#existing-private-deployments); do not repeat
staging or re-enable model public access.

## Prerequisites

Complete the [main prerequisites](../README.md#before-you-start) and
[shared setup](../README.md#shared-setup), retaining the existing input file and
state/backend. Do not run the public-path plan/apply. Additional requirements:

- Complete the [two-stage OTLP destination setup](monitoring.md) before planning
  the exporter. Keep the private profile on those plans too; readiness discovery
  must not re-enable a private model backend or rebuild the gateway.
- `Microsoft.Network` registered
- For the test VM: `Microsoft.Compute`, regional VM quota, and permission to use VM Run Command

### Test-client permissions

The Terraform deployment identity and the VM's managed identity have different
jobs. Creating role assignments alone does **not** authorize creating a custom
role definition.

| Identity | Required permission and scope |
| --- | --- |
| Terraform deployment identity | `Microsoft.Authorization/roleDefinitions/read`, `write`, and `delete` to manage the custom role through its lifecycle. The definition is addressed under the subscription, but its only `assignableScopes` entry is the gateway resource group. The identity must be authorized to manage definitions for that assignable scope. |
| Terraform deployment identity | `Microsoft.Authorization/roleAssignments/read`, `write`, and `delete` at the gateway resource for the VM's binding, in addition to the six service bindings and the exact OTLP DCR publisher binding. Respect managed-group deny assignments. |
| Test operator | Read the VM and its instance view; `Microsoft.Compute/virtualMachines/runCommand/action` to run the probe, `start/action` and `deallocate/action` for its power lifecycle, scoped to the test VM. |
| Test VM managed identity | Only `Microsoft.ApiManagement/service/apiKeys/listSecrets/action`, assigned **on the gateway resource**, not the subscription. Terraform creates this role/binding. |

Ask your subscription administrator to verify effective permissions, assignment
conditions and deny assignments **before enabling the VM**. Contributor alone
cannot manage RBAC, and Role Based Access Control Administrator does not by itself
grant custom role-definition management. Do not solve this by granting Owner to
the VM or broadening its key-reader role. See Microsoft's
[custom-role permissions](https://learn.microsoft.com/azure/role-based-access-control/custom-roles#who-can-create-delete-update-or-view-a-custom-role).
Deletion rights are needed for cleanup too; do not remove a role definition while
assignments still reference it.

If these permissions cannot be granted, keep `enable_private_test_client = false`
and use an approved existing private client with its own approved authentication.
This avoids the custom test-VM role, not the six core service roles or DCR publishing role.

## Step 1: Choose your test client

Your laptop is not on the VNet. The easiest option is the optional test VM (no VPN, no inbound SSH). Add these to `terraform.tfvars`:

```hcl
enable_private_test_client         = true
private_test_client_ssh_public_key = "ssh-ed25519 <your-public-key>"
```

- Use a **public** key only. Never paste a private key or password.
- The VM is billable, has no public IP and denies inbound traffic. The probe uses Run Command, not SSH.
- Already have a client on the VNet? Skip the VM and run equivalent DNS and inference checks from it. `Test-PrivateGateway.ps1` requires the VM.

## Step 2: Create networking with models temporarily public

Use this stage when adding private networking to an existing legacy gateway
whose model backend is still public. It is not the final posture, and it is not
a way to create a new legacy gateway.

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-var=models_public_network_access=Enabled" "-out=private-connectivity-stage1.tfplan"
```

Review the plan: gateway and model public access are both enabled, and networking
plus the VM (if enabled) are created. Do not apply unexpected replacements.

```powershell
terraform apply "private-connectivity-stage1.tfplan"
```

## Step 3: Check the private route

```powershell
.\scripts\Test-PrivateGateway.ps1
```

The wrapper runs the probe inside the VM, which must already be running. It checks
that the gateway and model hostnames resolve to the private endpoint subnet and
that every alias answers `OK`. The VM gets the gateway key through managed
identity. No key is printed or passed as an argument.

**Model prerequisite:** all aliases must support the probe's OpenAI Chat
Completions request, including `max_tokens` and `temperature`. The sample's
`gpt-4.1` and `gpt-4.1-mini` configuration is the reference. Responses-only,
embeddings, image, or other API formats need their own test. The probe rejects
incompatible API metadata before DNS/key retrieval; it does not interpret that
rejection as a networking failure. See [probe compatibility](reference.md#probe-compatibility).

**Stop if this fails.** Check endpoint approval, private DNS, permissions and outbound integration. A pass here is only an initial check, because model public access is still on.

## Step 4: Disable model public access

Plan **without** the temporary override:

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-out=private-connectivity.tfplan"
```

Expected change: model public access becomes `Disabled` (network ACL Deny). Gateway public access stays `Enabled`.

```powershell
terraform apply "private-connectivity.tfplan"
```

## Step 5: Prove the final private path

```powershell
.\scripts\Test-PrivateGateway.ps1
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" -detailed-exitcode
```

**Done when:** the probe reports `"passed": true` with `OK` for every alias, and the plan exits `0`.

The probe also rejects missing/invalid keys on the same route after positive
controls and emits per-call trace IDs. It does not itself verify all role
bindings, connections or telemetry ingestion.
Complete the [customer acceptance guide](acceptance.md) before handing over the
deployment, not the public-path plan/apply. A DNS/inference pass is only the
private-route part of acceptance. The [end-to-end runner](end-to-end.md) adds
VM lifecycle handling, backend checks, correlated telemetry and portal evidence.

## Step 6: Stop the VM when you are done

```powershell
$vmId = terraform output -raw private_test_vm_id
$subscriptionId = ($vmId -split '/')[2]
az vm deallocate --subscription $subscriptionId --ids $vmId
```

Restart with `az vm start` using the same arguments. Disks, private endpoints, DNS, model deployments and monitoring still incur charges.

## Existing private deployments

If you already have a working private backend with model public access disabled, start at Step 4, review the plan, then run Step 5.

Do not apply stale private-only plans, and do not re-enable public access as an automatic recovery step.
