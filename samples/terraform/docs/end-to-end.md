# Customer-like rehearsal and portal acceptance

The offline suite, live backend verifier and authenticated portal review are
separate gates. **None is a substitute for the other two.** The verifier never
deploys, repairs, grants roles, switches SKUs or deletes Azure resources.

## Scope and environment gate

Keep the legacy `AIGateway` SKU and private-endpoint architecture. All application
resources belong in one group; the VM's custom role definition is subscription
scoped, with its assignable scope limited to that group. Retained migration groups
must be cleaned up through a separately reviewed operation before final acceptance.
During a three-group migration, first use the manual private/runtime checks in
[acceptance.md](acceptance.md) to establish backend health before approving old-group
cleanup. The strict final runner deliberately does not waive its placement gate.

| Rehearsal | What it proves | Prerequisite |
| --- | --- | --- |
| Clean checkout, offline | Reproducible configuration and regression checks | No Azure credentials, state or customer input files |
| Existing legacy integration | Configuration and runtime of an existing gateway | Exclusive ownership of its authoritative state, approved inputs and scope |
| New customer / greenfield | Creation from scratch | Explicit product-group confirmation of legacy-SKU creation eligibility; currently documented as unsupported |

Do not call an integration pass a greenfield pass. A container sandbox can isolate
tools but cannot emulate Azure provisioning, quotas, Private Link, DNS, managed
identities, ingestion or the real portal. No hosted agent/image is deployed by
this sample, so image pull, artifact access and agent execution need a separate
approved test. Private routing is **not** private-only gateway ingress.

Before any new cloud rehearsal, record the approved subscription/tenant, regions,
unique environment name/group, model quota, permissions, cost ceiling, expiry,
cleanup owner and protected state location. Use a separate identity/state and
prefer a separate test subscription. A budget alert is not a hard spending cap.
Do not proceed without this approval and SKU eligibility. There is deliberately
no credentialed cloud deployment workflow yet.

For an existing deployment, preserve its backend/state, exact stable naming inputs
and any migration revision. Never copy its state into a second active environment.
For a genuinely new, eligible environment use `terraform.tfvars.example` plus the
published private profile, not another developer's local migration overrides.
Follow the [private guide](private-connectivity.md) for preflight and staged,
reviewed plan/apply. Inspect exact target IDs, public access, role scopes and every
destroy/replace action; retain gateway `prevent_destroy`. The acceptance runner is
**post-deployment**, not an automatic deployment controller.

## 1. Clean checkout and offline CI

Use an approved immutable commit in a separate checkout. Record its SHA. Run with
PowerShell 7, Terraform 1.11.4 and Python 3.12+ from `samples\terraform`:

```powershell
.\scripts\Test-Offline.ps1
```

This initializes with the committed provider lockfile in readonly mode, checks
format/validation, runs mocked Terraform tests and the Python/PowerShell suites.
Use a clean checkout without local tfvars/state for this step; initialization is
not a migration of an existing backend. CI runs this same command on Windows,
without Azure secrets, OIDC permissions or cloud deployment on pull requests.
Provider installation needs internet access; "offline" means no Azure operations.

## 2. Read-only backend checks

Reconnect the approved state/backend and supply its existing private inputs.
Ensure the checkout is clean, Terraform is initialized and Azure CLI is signed
into the approved context. These checks need resource/role read access; telemetry
also needs Application Insights query access.

```powershell
$parameters = @{
    SubscriptionId = '<approved-subscription-guid>'
    TenantId = '<approved-tenant-guid>'
    ResourceGroup = '<expected-shared-group>'
    ReportDirectory = 'C:\protected-evidence\gateway'
}
.\scripts\Test-CustomerAcceptance.ps1 @parameters
```

Reports go into a unique run-ID subdirectory. Store them outside the checkout or
in the ignored `acceptance-results` directory with access restricted to the test
team; IDs, IPs and screenshots still contain operational information. Do not
publish them to a public repository or an unrestricted CI artifact.

The default checks context, a clean source commit, single-group state placement,
live identities/resources/catalog/aliases, six exact service roles, three
connections, monitoring/exporter, endpoint provisioning **and** approval, DNS
links and a full drift plan. It does not start the VM, retrieve keys or call
models. Therefore runtime/telemetry remain NOT RUN/BLOCKED and it exits with an
incomplete-acceptance error, even if all read-only checks pass.

Every drift plan includes `profiles\private-connectivity.tfvars.json` last.
For additional explicitly approved nonautomatic input files use
`-AdditionalVarFile 'C:\protected-inputs\environment.tfvars'`. Existing automatic
tfvars still apply: review them and `TF_VAR_*` values. Remove hidden
`TF_CLI_ARGS`/`TF_CLI_ARGS_plan`; targeted plans are not acceptance. State, raw
plan text and raw service errors are never included in reports.

## 3. Explicit private runtime and telemetry

Only after approving model and VM costs:

```powershell
.\scripts\Test-CustomerAcceptance.ps1 @parameters -RunPrivateProbe -TelemetryWaitSeconds 300
```

This flag permits starting the **output-identified test VM**, running its probe
and deallocating it. It requires the VM to be initially deallocated so it will
not take over someone else's running session. All prerequisite checks must pass
before it starts. It verifies deallocation in `finally`, including probe failure.
If the process/machine is killed, `finally` cannot guarantee cleanup: the named
cleanup owner must check power state and deallocate the exact VM manually.
No cleanup failure is a pass.

The probe checks both DNS names inside the expected private subnet, makes one
positive chat call per alias (8 requested output tokens, 90-second HTTP timeout)
and then two same-route negative-key calls. Positives must return HTTP 200 and
exactly `OK`. Negative requests must fail with 401 or a key/authentication-specific
403; a generic firewall 403, 429, 500 or timeout is not authentication proof.
There is no load test or model-call retry. Existing managed-identity key lookup
retries at most 12 times, with 15-second waits for 403 propagation.

Each positive request sends a unique W3C `traceparent`. The verifier queries the
gateway's Application Insights for those exact `operation_Id` values and
successful HTTP 200 requests in the recorded UTC window, polling for at most the
configured ingestion wait (0-900 seconds, excluding individual CLI call duration).
It does **not** substitute historical traffic or exporter existence for delivery.
If this preview does not propagate W3C IDs into that schema, the check fails:
investigate actual exporter correlation support before changing the assertion.
Trace propagation and the telemetry schema still require real-environment proof.

`acceptance.json` reports each check and non-secret evidence. CLI/HTTP operations
can also have platform-level waits; this runner is not a hard wall-clock or cost
limiter. Use a supervised run and a separate cost/VM watchdog for unattended use.

## 4. AI Gateway portal review

Open **https://ai.gateway.azure.com** in an authenticated browser with the intended
corporate account, not a lab/admin account. Verify the actual tenant and selected
subscription/resource against the report. Use a client with VNet connectivity
when exercising the private route. A portal playground might call the enabled
public gateway endpoint; record its actual route and do not label it private proof.

The runner creates `portal-evidence.json`. Only begin final functional acceptance
after `backendStatus` is PASS. Earlier browsing is a **diagnostic baseline**, not
a full UI pass. Use actual current UI labels and controls; no unverified selectors
or assumptions about preview navigation are baked into the scripts.

| Check name | Required observation |
| --- | --- |
| `resource-context` | Correct tenant, subscription, shared group and gateway; no accidental resource/account switch after refresh |
| `configuration` | Provider/backend and every alias agree with the report/configuration; inspect details without saving changes |
| `playground` | One bounded benign call per alias, successful visible response, reported usage/errors sensible; record actual route and UTC times |
| `metrics` | Requests and available token/error/latency views load, use the selected resource/time filter, and show fresh test traffic; compare one positive numeric count with its underlying query using identical filters/aggregation |
| `error-states` | Clear empty state for a window with no traffic and understandable error for a safe unsupported alias/invalid key where the UI supports it; never delete resources or change policies to manufacture errors |
| `browser-health` | Navigation, refresh, loading/error completion and charts function; record durations, browser version, relevant console failures and failing request status codes without headers/bodies |

Record both usability observations and defects, not just a screenshot of a chart.
For missing/unsupported controls use FAIL/BLOCKED, not a fabricated PASS. Do not
mark requests/tokens as healthy while only displaying old or unrelated traffic.
With shared background traffic, compare the same resource/window/status filters
in the UI and backend query; do not assume the displayed total equals just the
probe count. Metrics definitions/rounding must match before comparing values.

For each checklist item fill `status`, `observed` and a relative `evidence` filename
for a redacted screenshot or observation text stored beside the manifest. Fill
`reviewer` and `reviewedUtc` only after the review. In `metrics`, record the
underlying `source` query/metric definition, UTC window (at most 24 hours and
covering the probe), numeric `portalValue` and `referenceValue`, and an
`explanation` of identical filters/aggregation. Never capture keys, sign-in screens,
authorization headers, connection strings or customer prompts; do not save HAR
files/raw network traces. The non-secret trace IDs in the backend report connect
the reference telemetry to this run.

```powershell
.\scripts\Complete-PortalAcceptance.ps1 `
    -BackendReport 'C:\protected-evidence\gateway\<run-id>\acceptance.json' `
    -PortalEvidence 'C:\protected-evidence\gateway\<run-id>\portal-evidence.json'
```

This validates context, completeness, evidence files and the metrics comparison
and writes a separate `acceptance-with-portal.json`. It **does not automate the
browser or independently verify the observations**: UI acceptance is explicitly
operator-attested. Failed backend checks cannot be overridden, and the original
backend report is preserved. No complete end-to-end PASS is emitted without both.

## 5. Repeatability, handover and cleanup

Rerun the same approved commit/inputs against the same exclusively owned state.
Require another zero-drift result and new runtime/telemetry/UI evidence; do not
reuse an old portal pass. An independent greenfield test remains a separate gate.
Keep failed reports and non-secret correlation IDs for support; never repeatedly
recreate a failing gateway endpoint without a diagnosed fix.

Hand over the approved commit, input/state ownership instructions, source CI
result, deployment evidence, both acceptance reports, known limitations and cleanup
owner. For teardown follow [protected cleanup](reference.md#cost-and-cleanup);
the runner does not disable gateway protection or automatically delete a group.
