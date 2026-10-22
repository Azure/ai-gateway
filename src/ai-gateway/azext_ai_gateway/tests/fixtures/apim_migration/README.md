# APIM V2 migration validation fixture

This fixture validates read-only APIM inventory behavior without making a
long-lived shared test environment. The provisioning script creates one new,
isolated resource group containing one healthy V2 APIM service, then adds
non-secret service- and workspace-scoped assets. It refuses an existing
resource group. Cleanup deletes the group only after matching both ownership
tags.

Provisioning is intentionally manual because V2 APIM creation is slow and
billable. **Do not run it in routine unit tests or CI.**

## Provision and inventory

Use a globally unique, disposable service name. The caller must already be
logged in to Azure CLI and authorized to create APIM and resource groups.

```bash
./src/ai-gateway/azext_ai_gateway/tests/fixtures/apim_migration/provision.sh \
  provision \
  --subscription 00000000-0000-0000-0000-000000000000 \
  --location eastus2 \
  --service-name aigw-migration-fixture-unique \
  --sku BasicV2
```

The script uses `az rest` with stable APIM API version `2024-05-01` because the
installed `az apim create` command may not expose V2 SKUs. It waits for a
healthy service before creating:

- a system-assigned identity and service policy;
- one non-secret named value and policy fragment;
- a credential-free HTTP backend;
- a service REST API, operation, API policy, and product relationship;
- a workspace with its own backend, REST API, and operation.

The script does not retrieve subscription keys, named-value secrets, tokens, or
certificate material. Azure CLI obtains its ARM token from the caller's active
login and keeps it in its normal runtime credential store. Do not enable shell
tracing around the script.

Run the inventory command printed by the script and save output only to an
access-controlled test artifact. Confirm `schemaVersion`, source ID, SKU,
provisioning states, complete required coverage, both scopes, representative
assets, and the absence of raw credentials.

Always clean up:

```bash
./src/ai-gateway/azext_ai_gateway/tests/fixtures/apim_migration/provision.sh \
  cleanup \
  --subscription 00000000-0000-0000-0000-000000000000 \
  --service-name aigw-migration-fixture-unique
```

If a provisioning step fails, inspect the retained resource group and invoke
the same cleanup command. Never retag an unrelated group to bypass the cleanup
guard.

## V2 SKU coverage

Run the live fixture once as `BasicV2`. For release qualification, repeat it in
separate resource groups with `StandardV2` and `PremiumV2`; never update an
existing fixture's SKU in place. Compare each inventory with
`healthySkuCases` in `mock-scenarios.json`. Keep networking disabled in the
baseline fixture so the live test remains portable; test each SKU's capability
evidence with recorded responses or mocks rather than provisioning VNets,
private endpoints, zones, or multi-region resources.

Service-level MCP is a preview enrichment and is not provisioned by this stable
baseline. Exercise MCP API typing and tools with a sanitized
`2025-09-01-preview` recording or request mocks. Workspace MCP must be asserted
as `notApplicable` without making a request.

## Recordings and mocks

Capture recordings only from this disposable fixture. Before committing one:

1. Replace subscription IDs, tenant IDs, resource-group and service names,
   gateway hostnames, request IDs, correlation IDs, timestamps, and identity
   principal/tenant IDs with stable placeholders.
2. Remove `Authorization`, cookies, APIM subscription keys, SAS values, access
   tokens, certificate bodies, named-value secret contents, and every response
   header not required by the test. Never invoke a secret-list operation to
   enrich a recording.
3. Preserve status codes, pagination links in placeholder form, API versions,
   resource shapes, SKU/capability fields, and retry headers used by assertions.
4. Scan the serialized recording for JWTs, UUIDs from the live subscription,
   `sig=`, `subscription-key`, and credential-bearing URLs.
5. Replay with outbound network disabled and verify deterministic ordering and
   redaction before accepting the recording.

Use request-layer mocks for failures that should not be induced against Azure.
`mock-scenarios.json` is the required matrix: non-retryable authentication and
authorization errors; policy versus collection `404`; retry exhaustion for
`408`, `429`, `500`, `502`, `503`, and `504`; partial and looping pagination;
required workspace failure; MCP preview failure with stable API preservation;
and deduplicated scale-unit-family `InvalidOperation` platform health.

For every fault, assert coverage status, observed/page counts, discovery
completeness, error category and retry behavior. Also assert that partial or
failed collections never establish absence and that safe request identifiers
do not affect semantic inventory fingerprints.
