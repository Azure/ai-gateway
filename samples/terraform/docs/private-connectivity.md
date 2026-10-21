# Private connectivity (optional)

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

> The profile does **not** make the gateway private-only, and it does not secure
> hosted-agent networking or prove agent execution.

## Prerequisites

Everything in the [main prerequisites](../README.md#before-you-start), plus:

- `Microsoft.Network` registered
- For the test VM: `Microsoft.Compute`, regional VM quota, and permission to use VM Run Command

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

Use this stage for a new deployment, or any deployment whose backend is still public. It is not the final posture.

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" "-var=models_public_network_access=Enabled" "-out=private-connectivity-stage1.tfplan"
```

Review the plan: gateway and model public access are both enabled, and networking plus the VM are created. Do not apply unexpected replacements.

```powershell
terraform apply "private-connectivity-stage1.tfplan"
```

## Step 3: Check the private route

```powershell
.\scripts\Test-PrivateGateway.ps1
```

The script runs inside the VM. It checks that the gateway and model hostnames resolve to the private endpoint subnet and that every alias answers `OK`. The VM gets the gateway key through managed identity. No key is printed or passed as an argument.

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

The probe does not test invalid keys or telemetry. Run the checks in the [main README](../README.md#quick-start-public-endpoints).

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
