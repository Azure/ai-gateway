# APIM import inventory specification

## Purpose

`az ai-gateway import-inventory` is the read-only discovery primitive for an
AI-assisted migration from Azure API Management (APIM) to the AI Gateway SKU.
It records migration-relevant source facts in a stable, versioned, redacted
schema.

The command deliberately does not:

- inspect or create a destination AI Gateway;
- classify source objects as importable or unimportable;
- choose source-to-destination mappings;
- build or execute a write plan;
- retrieve secret, key, certificate, or named-value contents.

Those responsibilities belong to the plugin's `migrate-ai-gateway` skill. The
skill combines this inventory with destination state, capability data, and
administrator decisions, then invokes granular Azure CLI commands.

## Source requirements

- The source is identified by a complete
  `Microsoft.ApiManagement/service` resource ID.
- Any APIM SKU can be inventoried. The SKU is retained as migration evidence;
  the skill decides whether source behavior has a destination equivalent.
- Discovery covers service scope and every accessible workspace.
- A policy singleton `404` is treated as an absent policy.
- Collection errors remain in `discoveryErrors`; required errors set
  `summary.discoveryComplete` to `false`. Failure to enumerate workspaces is
  required because otherwise workspace configuration could be mistaken for
  absence.

## Result envelope

The top-level result has this shape:

```json
{
  "schemaVersion": "3.0",
  "kind": "AiGatewayApimImportInventory",
  "source": {},
  "summary": {},
  "scopes": [],
  "apis": [],
  "relatedResources": {},
  "collectionCoverage": [],
  "healthIncidents": [],
  "discoveryErrors": [],
  "excludedResourceFamilies": [],
  "provenance": {},
  "domainAuthority": [],
  "sourceBehaviorLedger": []
}
```

Consumers must inspect `schemaVersion` before reading the result. Additive
fields may be introduced within a schema version. Removing a field or changing
its meaning requires a new schema version.

All arrays whose source ordering is not meaningful are sorted by stable
resource identity. Each API has `stableId` equal to its ARM resource ID.

## Export fallback and provenance

Live ARM discovery always runs. When a live domain is incomplete, callers may
provide local declarative evidence:

```bash
az ai-gateway import-inventory \
  --source-apim-id <complete-source-resource-id> \
  --apiops-artifact <local-file-or-directory> \
  --arm-template-file <local-arm-template.json> \
  --approve-export-evidence \
  --output json
```

`--apiops-artifact` is the first incomplete-domain fallback.
`--arm-template-file` is the conservative second fallback; ARM expressions are
not evaluated. `--approve-export-evidence` is required whenever either local
input is used. Neither option deploys the artifact or retrieves secrets.

`provenance.authorityOrder` is
`completeLiveArm`, `apiops`, `armTemplate`, then `partialLiveArm`. Complete live
observations remain authoritative. Export evidence normally fills only known
positive facts. A matching APIOps `inventory-metadata.json` completeness claim
may recover a failed live domain and establish completeness only when the claim
identifies the exact scope/domain and no conflict exists. ARM templates and
unclaimed APIOps omissions never prove absence. Conflicting facts remain in
`provenance.conflicts`; the selected value does not silently resolve the
migration decision. `domainAuthority` records the effective evidence role and
whether it establishes completeness for each attempted domain.

Every retained source fact includes redacted provenance. The deterministic
`sourceBehaviorLedger` assigns stable IDs to migration-relevant API, operation,
policy, backend, relationship, MCP, diagnostic, logger, and scoped-resource
behavior. Migration planning uses this ledger, rather than collection counts,
as its behavior-coverage boundary.

## Source summary

`source` contains:

- resource ID and name;
- location and SKU;
- SKU capacity, availability zones, sanitized custom hostname configuration,
  and additional-location metadata;
- gateway URL with credentials, query values, and fragments redacted;
- public network access, virtual-network type, subnet resource ID, and private
  endpoint connection count;
- system-assigned and user-assigned identity metadata.

`summary` contains API and workspace counts, discovery completeness, and the
number of discovery errors. `inventoryStatus` is `complete` only when every
attempted collection is `complete`, `empty`, or authoritatively
`notApplicable`; otherwise it is `partial`. Counts describe observed source
resources and do not imply migration support or absence in a partial domain.

## V2 SKU and API-version contract

BasicV2, StandardV2, and PremiumV2 share the ordinary APIM management surface.
Service, API, backend, policy, operation, workspace, and related-resource reads
use stable API version `2024-05-01`.

MCP is a separate preview enrichment. Service APIs are additionally queried
with `2025-09-01-preview` to preserve `type: mcp`, and `/apis/{id}/tools` uses
that preview version. MCP servers are unsupported inside workspaces, so the
command never probes workspace tool collections.

`source.migrationCompatibility` reports:

- whether the source is one of the three supported V2 SKUs;
- the stable and MCP API versions;
- versioned capability evidence for workspaces, service/workspace MCP,
  networking, availability zones, and multi-region behavior.

BasicV2, StandardV2, and PremiumV2 are all valid inventory sources. Their
networking capability differences are evidence for the migration skill, not a
reason to reject discovery.

## Collection coverage

Every attempted list operation emits a `collectionCoverage` record containing
scope, domain, API version, status, observed count, completed pages, and whether
the collection is required for enumeration.

Coverage status is one of:

- `complete`: the operation succeeded and returned resources;
- `empty`: the operation succeeded and returned no resources;
- `notApplicable`: versioned capability evidence says the collection cannot
  exist at that scope;
- `partial`: one or more pages succeeded before a later page failed;
- `failed`: no authoritative page was read.

A `404` from a collection is not automatically empty. Only a successful list
with zero values establishes emptiness. Policy singleton `404` means that
specific policy is absent. Partial pagination preserves observed items but can
never establish absence.

Read-only calls retry boundedly for `408`, `429`, `500`, `502`, `503`, and
`504`, honoring `Retry-After` or `x-ms-retry-after-ms`. Authorization and
permanent request failures are not retried blindly.

Repeated scale-unit-family `InvalidOperation` errors are collapsed into one
`platformHealth` incident with affected domains, safe request identifiers, and
remediation. This condition means the APIM resource provider cannot
consistently read the service; it is not evidence that a V2 SKU or collection
is unsupported.

## Scope and API inventory

`scopes` contains service and workspace entries with the API IDs observed in
each scope.

Every `apis[]` entry contains:

- stable resource identity and service/workspace scope;
- display, description, path, protocol, type, subscription requirement, and
  sanitized source properties;
- revision and version metadata;
- MCP properties;
- resolved backend summaries;
- policy summaries at API, inherited service/workspace, operation, and product
  scopes;
- operation definitions;
- product and subscription relationships;
- MCP tools and their backing API/operation dependencies;
- diagnostics and logger references.

No API is removed because it appears unsupported or because it backs another
API. For example, an MCP server and its REST backing API both remain in the
inventory so the skill can preserve their relationship.

## Discovery traversal

At service scope, discovery reads:

- the service resource and policy;
- backends and APIs;
- operations and operation policies;
- products associated with APIs and product policies;
- subscriptions;
- diagnostics and loggers;
- workspaces;
- service and workspace named values, policy fragments, products, and
  subscriptions;
- service certificates, groups, identity providers, and authorization providers.

For every workspace, discovery reads its policy, backends, APIs, operations,
products, MCP tools, diagnostics, and logger references.

Policy inheritance is represented, not flattened. An absent policy or a policy
containing `<base />` records inherited workspace/service policy summaries.

## Endpoint and backend facts

The inventory reports source API service URLs and resolved APIM backends. A
backend summary includes:

- ID and name;
- sanitized URL and protocol;
- Azure resource ID, when configured;
- whether credentials exist;
- credential header names, query parameter names, authorization scheme, and
  named-value references;
- recursively sanitized non-secret properties.

Credential values are never included. The inventory does not select an
effective destination endpoint or infer a destination provider.

## Policy facts

Raw policy XML is read only to produce a safe structural summary and is never
returned. A policy summary includes:

- scope and scope type;
- whether the policy is present and inherits its parent;
- parse errors;
- statement names and occurrences;
- section and control-flow context captured by statement occurrences;
- recognized and unsupported statement names;
- backend IDs referenced by routing statements;
- capability assessments from the policy support registry;
- managed-identity authentication intent without token values.

Deterministically translated destination policy objects are excluded from the
inventory. The migration skill queries
`az ai-gateway policy import-support list|show`, reviews scope and omitted
semantics, and records its proposal in the migration mapping artifact.

See [APIM policy translation](apim-policy-translation.md) for the capability
registry contract.

## Related resources

`relatedResources` contains migration-relevant service collections that are not
owned by a single API:

| Collection | Returned metadata |
| --- | --- |
| `namedValues` | ID, name, display name, secret flag, tags, and a redacted value marker |
| `certificates` | ID, name, subject, thumbprint, and expiration |
| `groups` | ID, name, display name, description, type, and external ID |
| `identityProviders` | ID, name, provider type, allowed tenants, and authority |
| `authorizationProviders` | ID, name, display name, and identity-provider metadata |

The inventory records dependencies and the presence of credentials, not live
credentials. Collections that are intentionally unrelated to AI Gateway
migration are named with reasons in `excludedResourceFamilies`.

## Discovery errors

Every discovery error contains:

- the failing ARM scope;
- HTTP status when available;
- a safe message;
- configuration domain;
- whether the data was required.

Required errors mean the source inventory is incomplete and the migration skill
must not treat absence as evidence. Optional errors may permit planning, but the
skill must retain them as warnings and determine whether they affect a proposed
migration unit.

## Redaction and non-retrieval rules

The implementation must satisfy all of these rules:

1. Never call subscription `listSecrets`, named-value `listValue`, provider-key,
   certificate-data, or another secret-returning operation.
2. Never return raw policy XML.
3. Replace secret-bearing property values with `<redacted>`.
4. Return credential structure and reference names without credential values.
5. Remove URL user information and redact every query value and fragment.
6. Preserve enough resource identity to let the migration skill request a
   credential securely at execution time without embedding it in an artifact.
7. Keep discovery error messages free of source secrets.

## Determinism and portability

- The schema 3.0 JSON result is suitable for a portable local migration
  workspace.
- Table output is a summary only and is not an input to migration reasoning.
- The command has no dependency on destination state.
- Re-running against unchanged source state produces semantically equivalent,
  deterministically ordered output.
- The result contains no process-local object, temporary URL, or secret that
  prevents safe persistence after the administrator agrees to create local
  migration artifacts.

## Skill contract

The migration skill consumes this inventory and must:

1. inventory the selected destination separately;
2. preserve every source behavior as `ready`, `needs-input`, or
   `cannot-import`, with explicit residual handling where required;
3. bind destination capability evidence to
   `az ai-gateway migration-capability show -o json`;
4. cite source authority/provenance and stable capability IDs for each mapping;
5. ask the administrator rather than silently approximating ambiguous
   semantics;
6. validate the generated context, mapping, and TODO graph with
   `az ai-gateway migration-plan validate` before approval or execution;
7. persist only redacted decisions and TODO state;
8. resolve secrets only at execution time;
9. apply approved work through supported granular Azure CLI commands;
10. verify destination resources and source behavior separately;
11. require explicit current-plan acceptance for every residual;
12. report `complete` only for fully behavior-verified work, or
    `complete-with-accepted-residuals` when every remaining residual is
    explicitly accepted.
