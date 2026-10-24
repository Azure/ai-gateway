# Customer acceptance for an existing deployment

Use this after the chosen [networking path](../README.md#choose-your-networking-path)
has been applied successfully. It is **not** a new-deployment or recovery guide.
The [legacy-resource limitation](reference.md#resource-type-and-lifecycle) and
**Pending private-only gateway ingress** remain in effect.

**Automated private-profile entrypoint:** follow the [end-to-end runbook](end-to-end.md)
and `scripts\Test-CustomerAcceptance.ps1` for executable checks, sanitized reports,
same-private-route negative authentication, correlated telemetry and a separate
portal/metrics review. The detailed blocks below remain useful for manual
diagnosis and the public path; do not run them as a second billable test by default.

Run the PowerShell blocks in order, in the same PowerShell **7** session, from
`samples\terraform`. Keep the original inputs and state/backend. Do not print raw
state, ARM responses, connection credentials, keys or telemetry connection strings.
These checks do not grant permissions or repair resources. Inference is billable.

## 1. Confirm the target and read live resource identities

Replace both placeholders with the approved customer context. The operator needs
resource/role-assignment read access and permission to query the gateway's
Log Analytics workspace and linked AMW Prometheus endpoint. Running the private probe also requires the
[test-client permissions](private-connectivity.md#test-client-permissions).

```powershell
$ErrorActionPreference = 'Stop'
$subscription = '<subscription-id>'
$tenant = '<tenant-id>'
$accountJson = az account show --subscription $subscription --output json --only-show-errors
if ($LASTEXITCODE -ne 0) { throw 'Cannot read the approved Azure context.' }
$account = $accountJson | ConvertFrom-Json
if ($account.id -ne $subscription -or $account.tenantId -ne $tenant) {
    throw 'Subscription/tenant mismatch. Stop; do not change context automatically.'
}
$outputJson = terraform output -json
if ($LASTEXITCODE -ne 0) { throw 'Cannot read deployment outputs.' }
$o = $outputJson | ConvertFrom-Json

function Read-ArmUrl([string]$Url) {
    $prefix = "https://management.azure.com/subscriptions/$subscription/"
    if (-not $Url.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Unexpected ARM read scope.'
    }
    $json = az rest --subscription $subscription --method get --url $Url --output json --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw 'ARM read failed; acceptance is incomplete.' }
    $json | ConvertFrom-Json -Depth 50
}
function Get-Arm([string]$Id, [string]$Version) {
    Read-ArmUrl "https://management.azure.com${Id}?api-version=$Version"
}
function Get-ArmItems([string]$Id, [string]$Version) {
    $url = "https://management.azure.com${Id}?api-version=$Version"
    while ($url) {
        $page = Read-ArmUrl $url
        $page.value
        $url = $page.nextLink
    }
}

$gatewayId = [string]$o.gateway_id.value
$modelsId = [string]$o.foundry_models_id.value
$projectId = [string]$o.project_id.value
$agentsId = $projectId -replace '/projects/[^/]+$', ''
$agentsGroup = "/subscriptions/$subscription/resourceGroups/$($o.resource_groups.value.agents)"
$storageId = "$agentsGroup/providers/Microsoft.Storage/storageAccounts/$($o.storage_account_name.value)"
$registryName = ([string]$o.container_registry_endpoint.value).Split('.')[0]
$registryId = "$agentsGroup/providers/Microsoft.ContainerRegistry/registries/$registryName"
$gateway = Get-Arm $gatewayId '2025-09-01-preview'
$models = Get-Arm $modelsId '2025-04-01-preview'
$agents = Get-Arm $agentsId '2025-04-01-preview'
$project = Get-Arm $projectId '2025-04-01-preview'
$storage = Get-Arm $storageId '2024-01-01'
$registry = Get-Arm $registryId '2023-07-01'
foreach ($resource in @($gateway, $models, $agents, $project, $storage, $registry)) {
    if ($resource.properties.provisioningState -ne 'Succeeded') {
        throw "Resource is not ready: $($resource.id)"
    }
}
foreach ($resource in @($gateway, $project)) {
    if (-not $resource.identity.principalId -or $resource.identity.tenantId -ne $tenant) {
        throw "Missing or wrong-tenant managed identity: $($resource.id)"
    }
}
'Target resources and runtime principal IDs verified.'
```

**Expected:** the final message. A `404`, access denial, failed provisioning or
missing identity is a failure, not permission to recreate a resource.

## 2. Verify the six exact service role bindings

Compare **current live identities**, resource scopes and role-definition IDs.
Do not substitute an old principal ID, accept an assignment on the wrong
resource, or count unrelated/inherited roles as proof of the configured binding.

```powershell
$bindings = @(
    @{ name = 'gateway-foundry-user'; principal = $gateway.identity.principalId; scope = $modelsId; role = '53ca6127-db72-4b80-b1b0-d745d6d5456d' }
    @{ name = 'project-storage'; principal = $project.identity.principalId; scope = $storageId; role = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' }
    @{ name = 'project-acr-pull'; principal = $project.identity.principalId; scope = $registryId; role = '7f951dda-4ed3-4680-a7ca-43fe172d538d' }
    @{ name = 'project-contributor'; principal = $project.identity.principalId; scope = $agentsId; role = '25fbc0a9-bd7c-42a3-aa1a-3b75d497ee68' }
    @{ name = 'project-openai-user'; principal = $project.identity.principalId; scope = $agentsId; role = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' }
    @{ name = 'project-user'; principal = $project.identity.principalId; scope = $agentsId; role = 'a97b65f3-24c7-4388-baec-2e87135dc908' }
)
foreach ($binding in $bindings) {
    $roleId = "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/$($binding.role)"
    $assignments = @(Get-ArmItems "$($binding.scope)/providers/Microsoft.Authorization/roleAssignments" '2022-04-01')
    $match = @($assignments | Where-Object {
        $_.properties.scope -ieq $binding.scope -and
        $_.properties.principalId -eq $binding.principal -and
        $_.properties.principalType -eq 'ServicePrincipal' -and
        $_.properties.roleDefinitionId -ieq $roleId -and
        -not $_.properties.condition
    })
    if ($match.Count -ne 1) { throw "Expected exactly one configured binding: $($binding.name)" }
    "$($binding.name): verified"
}
```

**Expected:** six `verified` lines. Optional developer roles are additional and
must be reviewed against the explicitly approved `developer_principal_id` and
`rbac.tf`; their existence does not replace these six bindings. The optional VM's
key-reader binding is separate: inspect its gateway-scoped assignment and custom
role in **Gateway > Access control (IAM)** using the scope/action table in the
[private guide](private-connectivity.md#test-client-permissions). The private probe
also exercises that VM identity's ability to retrieve the key.

## 3. Verify the Foundry connections and gateway backend

```powershell
$projectConnections = @(Get-ArmItems "$projectId/connections" '2025-04-01-preview')
$accountConnections = @(Get-ArmItems "$agentsId/connections" '2025-06-01')
$expectedConnections = @(
    @{ name = $storage.name; items = $projectConnections; category = 'AzureStorageAccount'; auth = 'AAD'; target = $storage.properties.primaryEndpoints.blob; resource = $storageId }
    @{ name = "$($registry.name)-conn"; items = $projectConnections; category = 'ContainerRegistry'; auth = 'ManagedIdentity'; target = $registry.properties.loginServer; resource = $registryId }
    @{ name = ([string]$o.application_insights_ids.value.agents).Split('/')[-1]; items = $accountConnections; category = 'AppInsights'; auth = 'ApiKey'; target = $o.application_insights_ids.value.agents; resource = $o.application_insights_ids.value.agents }
)
foreach ($expected in $expectedConnections) {
    $match = @($expected.items | Where-Object {
        $_.name -eq $expected.name -and
        $_.properties.category -eq $expected.category -and
        $_.properties.authType -eq $expected.auth -and
        $_.properties.target -eq $expected.target -and
        $_.properties.metadata.ResourceId -ieq $expected.resource
    })
    if ($match.Count -ne 1) { throw "Missing or incorrect connection: $($expected.name)" }
    "$($expected.name): target/authentication metadata verified"
}
$provider = Get-Arm "$gatewayId/workspaces/default/modelProviders/foundry" '2025-09-01-preview'
$foundry = $provider.properties.foundry
if ($foundry.authentication.kind -ne 'ManagedIdentity' -or
    $foundry.authentication.managedIdentity.resource -ne 'https://cognitiveservices.azure.com/' -or
    @($foundry.resourceIds).Count -ne 1 -or $foundry.resourceIds[0] -ine $modelsId -or
    ([string]$foundry.endpoint).TrimEnd('/') -ne ([string]$models.properties.endpoint).TrimEnd('/')) {
    throw 'Incorrect gateway-to-model backend/authentication.'
}
'Gateway model provider verified.'
```

**Expected:** three connection confirmations and the provider confirmation.
This verifies configuration metadata, **not** credential contents, Storage
object access, an ACR image pull or running hosted agents. The sample deploys no
agent/image. If agent execution is a customer requirement, require a separate
approved image-pull, artifact-access and agent-execution test before signing off;
do not label these checks as an agent-runtime pass.

## 4. Exercise every alias on the intended route

Check [probe compatibility](reference.md#probe-compatibility) first. Record the
UTC start/end times and the per-alias results without keys or prompts containing
customer data.

For the **private path**, run `.\scripts\Test-PrivateGateway.ps1` from the
[private guide](private-connectivity.md#step-5-prove-the-final-private-path) with
the test VM running. Verify the live model account still has
`publicNetworkAccess = Disabled` and `networkAcls.defaultAction = Deny`; the
gateway currently remains `Enabled`. Both private endpoints must report
`Succeeded` and `Approved`:

```powershell
if ($models.properties.publicNetworkAccess -ne 'Disabled' -or
    $models.properties.networkAcls.defaultAction -ne 'Deny' -or
    $gateway.properties.publicNetworkAccess -ne 'Enabled' -or
    $gateway.properties.virtualNetworkType -ne 'External' -or
    -not $gateway.properties.virtualNetworkConfiguration.subnetResourceId) {
    throw 'Live network posture does not match the current private profile.'
}
foreach ($name in @('gateway', 'models')) {
    $endpoint = Get-Arm $o.private_endpoint_ids.value.$name '2024-05-01'
    $connections = @($endpoint.properties.privateLinkServiceConnections)
    $target = if ($name -eq 'gateway') { $gatewayId } else { $modelsId }
    if ($endpoint.properties.provisioningState -ne 'Succeeded' -or
        $connections.Count -ne 1 -or
        $connections[0].properties.privateLinkServiceConnectionState.status -ne 'Approved' -or
        $connections[0].properties.privateLinkServiceId -ine $target) {
        throw "Private endpoint is not ready or targets the wrong resource: $name"
    }
}
$testStartUtc = [DateTimeOffset]::UtcNow
.\scripts\Test-PrivateGateway.ps1
$testEndUtc = [DateTimeOffset]::UtcNow
```

**Expected:** `"passed": true`, both DNS names resolving exclusively inside the
configured endpoint subnet, and HTTP `200`/`OK` for **every** alias. Keep equivalent
evidence if using your own private client. Deallocate the optional VM in a
`finally` block when automating, or follow Step 6 of the private guide immediately
after testing, **including on failure**. Verify `az vm get-instance-view
--subscription <subscription-id> --ids <vm-id> --query instanceView.statuses
--output table` contains `PowerState/deallocated`; a merely stopped VM is not enough.

For the **public path only**, instead record the times around
`.\scripts\Test-ModelAliases.ps1`; every alias must return nonempty text.
Do not run the public-path Terraform plan against a private deployment.

## 5. Reject missing and invalid runtime keys

The following PowerShell 7 check runs on the **operator's machine** against the
currently enabled public gateway endpoint, including when the backend uses the
private profile. It is a separate authentication check, **not** evidence of
private routing or network isolation. Use the same reachable endpoint/alias that
passed a valid-key call; the private VM result alone does not establish public
reachability. If required, perform an approved public positive call with
`Test-ModelAliases.ps1` first (no infrastructure change; uses the operator's
key-read permission). Do not enable public access or grant extra permissions
automatically to make a test pass.

```powershell
$gatewayUrl = ([string]$o.gateway_endpoint.value).TrimEnd('/')
$alias = @($o.model_deployment_ids.value.PSObject.Properties.Name)[0]
$body = @{ model = $alias; messages = @(@{ role = 'user'; content = 'Say hello.' }) } |
    ConvertTo-Json -Depth 5
foreach ($case in @(
    @{ name = 'missing-key'; headers = @{} },
    @{ name = 'invalid-key'; headers = @{ 'Api-Key' = 'intentionally-invalid-acceptance-key' } }
)) {
    $response = Invoke-WebRequest -Method Post `
        -Uri "$gatewayUrl/default/models/openai/v1/chat/completions" `
        -Headers $case.headers -ContentType 'application/json' -Body $body `
        -SkipHttpErrorCheck -MaximumRedirection 0 -TimeoutSec 90
    if ([int]$response.StatusCode -notin @(401, 403)) {
        throw "Authentication check failed: $($case.name), HTTP $($response.StatusCode)"
    }
    "$($case.name): HTTP $($response.StatusCode)"
}
```

**Expected:** two gateway authentication rejections (`401` or `403`); inspect
the response locally to distinguish gateway authentication from a proxy/firewall
denial. A successful valid-key control on the **same path**, followed by both
rejections, is required. DNS/TLS/timeouts, redirects, `404`, `429`, or a generic
network `403` do **not** pass this check. If this route cannot be exercised, record
it as **not verified**, or run equivalent requests from an approved private
client with a same-path valid-key control. Do not copy runtime keys into commands,
reports or screenshots.

## 6. Verify telemetry delivery, not just exporter existence

Complete [OTLP setup](monitoring.md) first. Keep the six service role checks above;
the DCR publishing role below is an additional, narrowly scoped assignment.

```powershell
$destination = .\scripts\Get-GatewayMonitoring.ps1 -SubscriptionId $subscription `
    -ApplicationInsightsId $o.application_insights_ids.value.gateway `
    -ExpectedLogAnalyticsId $o.gateway_monitoring.value.log_analytics_id
$exporter = Get-Arm "$gatewayId/workspaces/default/telemetryExporters/appinsights" '2025-09-01-preview'
if ($exporter.properties.kind -ne 'OpenTelemetry' -or
    $exporter.properties.payloadCapture -ne $false -or
    $exporter.properties.applicationInsights.resourceId -ine $destination.insightsId -or
    $exporter.properties.openTelemetry.credentials.managedIdentity.resource -cne 'https://monitor.azure.com') {
    throw 'Incorrect telemetry exporter target or payload-capture setting.'
}
foreach ($name in @('metricsEndpoint', 'logsEndpoint', 'tracesEndpoint')) {
    if ($exporter.properties.openTelemetry.$name -cne $destination.endpoints[$name]) { throw "Incorrect $name." }
}
$publishing = @(Get-ArmItems "$($destination.dataCollectionRuleId)/providers/Microsoft.Authorization/roleAssignments" '2022-04-01' |
    Where-Object {
        $_.properties.scope -ieq $destination.dataCollectionRuleId -and
        $_.properties.principalId -eq $gateway.identity.principalId -and
        $_.properties.principalType -eq 'ServicePrincipal' -and -not $_.properties.condition -and
        $_.properties.roleDefinitionId -ieq "/subscriptions/$subscription/providers/Microsoft.Authorization/roleDefinitions/3913510d-42f4-4e42-8a64-420c390055eb"
    })
if ($publishing.Count -ne 1) { throw 'Exact DCR publishing role not verified.' }
$destination.logAnalyticsId
$testStartUtc.ToString('o')
$testEndUtc.ToString('o')
```

Open **that gateway Log Analytics workspace > Logs** (not agent insights).
Allow several minutes for ingestion; replace the time bounds and trace IDs below
with the recorded probe values. The automated runner additionally enforces
successful gateway server-span status and scoped Prometheus metrics.

```kusto
union withsource=TelemetryTable OTelSpans, OTelLogs
| where TimeGenerated between (datetime(2026-01-01T12:00:00Z) .. datetime(2026-01-01T12:15:00Z))
| where TraceId in ("<first-probe-trace-id>", "<second-probe-trace-id>")
| project TimeGenerated, TelemetryTable, TraceId
| order by TimeGenerated asc
```

**Expected:** new gateway request/related telemetry attributable to the test
window and model requests, including successful calls. Inspect trace IDs and
available alias/path dimensions locally to distinguish unrelated concurrent
traffic. Do not export full `customDimensions`, request/response bodies or
credentials. If the preview emits a different schema, use the resource's actual
tables and record that schema; a query error, empty result, or exporter existence
alone is **not** proof of delivery. Do not enable payload capture to troubleshoot
this acceptance check. Retest after ingestion delay; unresolved delivery is an
open acceptance item, not a silent pass.

Also verify fresh `azure.ai_gateway.client.token.usage` through the destination's
Prometheus endpoint, with the same Insights/workspace/time filters as the portal.
Use the query and interpretation in the [automated runbook](end-to-end.md):
positive metric samples are not an exact token total for just your calls.

## 7. Finish with a drift check and explicit acceptance record

For a private deployment:

```powershell
terraform plan "-var-file=profiles\private-connectivity.tfvars.json" -detailed-exitcode
switch ($LASTEXITCODE) {
    0 { 'No pending Terraform changes.' }
    1 { throw 'Plan failed; acceptance is incomplete.' }
    2 { throw 'Pending changes require review; do not apply automatically.' }
    default { throw 'Unexpected Terraform exit code.' }
}
```

For an intentionally public deployment, omit **only** the private `-var-file`
argument, retaining all its usual approved inputs/backend. Never omit it for a
private deployment. Keep plan output protected because it can contain secrets.

Record subscription/tenant, resource IDs, timestamp, Git revision, selected
profile, aliases tested, six service bindings plus the DCR publishing role, connection metadata, authentication
statuses, telemetry evidence, drift exit code and VM power state. Mark every item
**passed**, **failed** or **not verified**; do not include keys or raw state.

Acceptance remains limited to the demonstrated gateway/model route. Explicitly
record the still-public gateway endpoint and Pending private-only investigation.
If the customer requires private-only ingress, unsupported model tests, or
hosted-agent execution not demonstrated above, those requirements remain
**unmet** regardless of other checks passing.
