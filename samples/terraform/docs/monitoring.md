# Gateway OpenTelemetry setup

The current AI Gateway portal requires **OpenTelemetry**, the existing Application
Insights resource ID, and all three OTLP endpoints. A legacy connection-string
exporter, or merely changing its casing, does not establish this configuration.
The gateway uses its system identity with audience `https://monitor.azure.com`
and Monitoring Metrics Publisher (`3913510d-42f4-4e42-8a64-420c390055eb`) at the
**actual OTLP data collection rule (DCR)**. Payload capture stays disabled.
Agent Insights and its connection string are unchanged.

## Ownership, permissions and cost

All application resources, including both Insights components and Log Analytics
workspaces, remain in the shared application group. Enabling
`AzureMonitorWorkspaceIngestionMode` on gateway Insights can create an Azure
Monitor workspace (AMW), DCRs, data collection endpoints (DCEs) and **Azure-managed
helper groups**. The AMW default DCR/DCE can differ from the OTLP-specific pair.
These are service-owned dependencies, not additional application stacks.
Do not import, recreate or independently manage them with Terraform.

Review these side effects and ingestion/query/retention charges before enabling.
Terraform's action count does not enumerate service-created resources. Restoring
the old exporter is **not** a complete rollback: helper resources/data and costs
can remain. Deleting them or disabling OTLP needs a separately reviewed plan.

`Microsoft.Monitor`, `Microsoft.Insights` and `Microsoft.OperationalInsights` must
be registered. This sample does not register providers/features or bypass
eligibility, policy or managed-group deny assignments. Grant the one publishing
role directly on the linked DCR; do not use a nested ARM deployment in a protected
group or broaden scope to work around denial. Query operators separately need
Log Analytics query access and AMW Prometheus query access. Publisher access is
not reader access.

## Two-stage bootstrap or legacy-exporter upgrade

Use the existing authoritative state and approved inputs. Keep the private
profile on **every** plan for private deployments. Do not use these targeted
plans as final drift/acceptance evidence. No command below should be applied
without reviewing its saved plan and service-side effects.

**Stage A: enable only the destination.** From `samples\terraform`:

```powershell
terraform plan '-target=azapi_resource.insights["gateway"]' `
    '-var-file=profiles\private-connectivity.tfvars.json' '-out=monitoring-destination.tfplan'
if ($LASTEXITCODE -ne 0) { throw 'Destination plan failed.' }
# Review and approve the saved plan before running:
terraform apply 'monitoring-destination.tfplan'
if ($LASTEXITCODE -ne 0) { throw 'Destination apply failed; do not continue.' }
```

For an existing deployment this must be **one in-place gateway Insights update**,
with the same resource ID and Log Analytics association. Stop on gateway, agent,
network or other changes, especially replacement/deletion. A genuinely new,
explicitly eligible legacy deployment also creates prerequisite group/Log
Analytics resources; review those separately. Targeting cannot bypass SKU
creation restrictions.

**Discover and verify readiness without copying generated IDs:**

```powershell
$metadata = terraform output -json gateway_monitoring
if ($LASTEXITCODE -ne 0) { throw 'Cannot read monitoring metadata.' }
$metadata = $metadata | ConvertFrom-Json
$destination = .\scripts\Get-GatewayMonitoring.ps1 `
    -SubscriptionId '<approved-subscription-guid>' `
    -ApplicationInsightsId $metadata.insights_id `
    -ExpectedLogAnalyticsId $metadata.log_analytics_id -WaitSeconds 120
$destination | ConvertTo-Json -Depth 5
```

This is read-only. It waits for enablement, endpoints and DCR linkage, then checks
provisioning, DCR/DCE endpoint ownership, AMW and the existing Log Analytics
destination. It verifies that every linked external group is managed by this
Insights component or AMW. Unknown topology, auth failure or timeout stops the
process; nothing falls back to a guessed endpoint or a broader scope.
The wait excludes individual CLI request durations. The helper accepts
`DataCollectionRuleResourceId` or an ARM-form `DataCollectionRuleId`.
**Immutable-only linkage is not supported by this implementation**: stop and
resolve the service metadata; do not invent an ARM ID or manually edit state.
Non-Succeeded linked resources also stop the check; rerun read-only after
investigating rather than repeatedly mutating the exporter.

**Stage B: refresh, plan and review the exporter/role.** For a bounded repair:

```powershell
terraform plan '-target=azapi_resource.telemetry_exporter' `
    '-var-file=profiles\private-connectivity.tfvars.json' '-out=monitoring-exporter.tfplan'
if ($LASTEXITCODE -ne 0) { throw 'Exporter plan failed.' }
# Review and approve the saved plan before running:
terraform apply 'monitoring-exporter.tfplan'
if ($LASTEXITCODE -ne 0) { throw 'Exporter apply failed.' }
```

Dependencies include the publisher role and existing gateway; targeting is not
a guarantee of scope. For an existing legacy-exporter repair expect exactly one
DCR role creation and one in-place exporter update. Stop for anything else.
If the service rejects changing exporter kind in place, stop and obtain specific
approval for deletion/recreation; this sample does not pre-delete or auto-retry.
For a new eligible environment use the normal full networking-path plan after
Stage A readiness, reviewing all application creations instead.

### Existing legacy exporter: immutable kind

The legacy API has returned `ValidationError` with
`Telemetry exporter kind cannot be changed after creation.` for an existing
connection-string exporter. Terraform's planned in-place update does not prove
that the service permits it. The publisher role can already have been created
before that failure; preserve the resulting state and verify the actual role.

Prepare a **new**, explicitly reviewed replacement plan rather than retrying the
failed plan, deleting resources manually, or restoring old state:

```powershell
terraform plan '-target=azapi_resource.telemetry_exporter' `
    '-replace=azapi_resource.telemetry_exporter' `
    '-var-file=profiles\private-connectivity.tfvars.json' `
    '-out=monitoring-exporter-replacement.tfplan'
if ($LASTEXITCODE -ne 0) { throw 'Exporter replacement plan failed.' }
```

For a failed Stage B where the publisher already exists, require exactly one
delete/create replacement of `azapi_resource.telemetry_exporter`, with the same
name and parent, and **no other resource actions**. Recheck the destination and
publisher before explicit destructive-action approval. Only then apply the
reviewed saved plan. This does not replace the gateway or delete monitoring
storage/data. It is not atomic: the old exporter is removed first, and if
creation fails the exporter can remain absent. Stop for separately approved
recovery rather than silently retrying or rolling back.

Terraform refresh reads the real endpoints/DCR from Insights; no portal setup,
new provider or manual endpoint/ID input is required for supported metadata.
Allow propagation, then run a fresh **full**, untargeted drift plan and the
[acceptance gates](end-to-end.md). A targeted repair does not fix unrelated
Private Link, HTTP 500, retained-group or drift failures.

## Delivery and portal evidence

The private acceptance runner queries **OTelSpans** and **OTelLogs** in the linked
Log Analytics workspace using W3C `TraceId`. It requires successful gateway server
spans for every test call and at least one correlated log. No log observed means
logs delivery is **unproven**, not that successful requests must always log.
Investigate source emission before changing this gate.

It queries `azure.ai_gateway.client.token.usage` at the linked AMW's Prometheus
endpoint, scoped by `microsoft.appresourceid`, `azure.ai_gateway.workspace` and
the test window. Positive fresh samples prove scoped metrics activity, **not**
an exact token total attributable only to this run. The metric query excludes
pre-window samples carried forward by Prometheus lookback. Shared concurrent
traffic still needs matching portal/backend filters and aggregation.
Do not substitute classic `requests.operation_Id`, historical traffic, exporter
existence or a screenshot of an empty chart for all three signal paths.

Live service behavior and UI delivery are still deployment-time acceptance gates;
offline fixtures alone do not prove the preview works in a subscription.

## Troubleshooting identity and delayed ingestion

An ARM `principalId`, `Succeeded` provisioning state and matching role assignments
do **not** prove that the gateway's managed identity still exists. If inference
and telemetry fail together, verify the exact principal in the correct Entra
tenant. An authorized Graph check of the active service principal, deleted items
and directory audit can distinguish a deleted identity from an access or tenant
error. A failed or unauthorized lookup alone is not proof of deletion.

Deleted managed identities cannot be restored through Graph. A confirmed orphan
requires a separately reviewed identity repair on the existing resource, followed
by replacement of its original-scope role assignments and Terraform state
reconciliation. Identity removal/re-enablement is not atomic and can affect other
dependencies, including Key Vault-backed certificates. Do not automatically reset
an identity, recreate the gateway or reuse a plan from before the identity change.

Allow **up to 30 minutes** for the DCR publisher role to propagate before treating
an ingestion `403` as a persistent failure. This is separate from destination
provisioning and from the additional time needed for accepted records to appear
in Log Analytics. After propagation, generate a fresh bounded gateway request:
older spans may no longer be retried. Check its exact trace ID, correlated logs
and fresh, resource-scoped token samples rather than relying on old traffic.

A separately authorized synthetic OTLP trace can test the destination without
changing the exporter. Require both successful submission and the exact stored
trace; a `2xx` alone proves acceptance, not query visibility. Mark synthetic data,
exclude it from gateway acceptance, and remove any temporary publishing role.
Verify real gateway traffic independently afterward.

Token counters and trace-backed call counts can recover with different historical
coverage. Compare before/after counter samples with response usage; do not assume
that the portal's selected-range token total belongs entirely to the newest test.

## Sources

- [Official exact legacy API/SKU exporter example](https://github.com/Azure-Samples/AI-Gateway/blob/1679e3137d2fe7592d2a668d77ff71550d35b69e/modules/ai-gateway/v1/ai-gateway.bicep)
- [Complete lab, including DCR-scoped publishing](https://github.com/Azure-Samples/AI-Gateway/tree/main/labs/aigw-foundry-models)
- [Portal monitoring migration release](https://ai.gateway.azure.com/docs/releases/2026-08-28)
- [Direct OTLP ingestion](https://learn.microsoft.com/azure/azure-monitor/containers/opentelemetry-protocol-ingestion)
- [AMW managed infrastructure](https://learn.microsoft.com/azure/azure-monitor/metrics/azure-monitor-workspace-manage)
- [Managed identity deletion and token caching](https://learn.microsoft.com/entra/identity/managed-identities-azure-resources/managed-identities-faq)
- [API Management managed identity lifecycle](https://learn.microsoft.com/azure/api-management/api-management-howto-use-managed-service-identity)
- [DCR publisher permissions and propagation](https://learn.microsoft.com/azure/azure-monitor/logs/tutorial-logs-ingestion-portal#assign-permissions-to-the-dcr)
