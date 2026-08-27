# APIM policy translation

`az ai-gateway import --dry-run` inventories APIM policies and projects only
semantics represented by the AI Gateway control-plane contract. Policy
translation is intentionally conservative: unknown, conditional, scoped, or
lossy behavior is reported rather than silently discarded.

## Query the support registry

The extension exposes the same registry used by the import implementation:

```bash
az ai-gateway policy import-support list --output table
az ai-gateway policy import-support list --support-level unsupported
az ai-gateway policy import-support show --name llm-token-limit
```

Each entry reports its documentation URL, valid APIM scopes and sections,
applicable destination assets and subtypes, destination capability,
`supportLevel` (`exact`, `reduced`, or `unsupported`), assessment action
(`import`, `warn`, or `block`), criticality, omitted behavior, remediation
guidance, and executable handler linkage.

The machine-readable source of truth is
`azext_ai_gateway/apim_policy_index.json`. It inventories the current Microsoft
Learn APIM policy reference plus legacy AI policy statement names still
recognized by the importer. `_policy_translation.py` loads that file and binds
its `import` entries to `POLICY_TRANSLATORS` or
`POLICY_CONFIGURATION_HANDLERS`. Tests require every imported entry to resolve
to its declared executable handler.

## Current compatibility

| APIM policy | Level | Destination | Behavior |
| --- | --- | --- | --- |
| `llm-token-limit` | Reduced | `tokenLimit` | Translates literal per-minute rates and hourly/daily quotas. |
| `azure-openai-token-limit` | Reduced | `tokenLimit` | Uses the `llm-token-limit` mapping. |
| `llm-content-safety` | Reduced | `contentSafety` | Translates literal harm-category thresholds. |
| `set-backend-service` | Reduced | Backend resolution | Uses `backend-id`; warns for `base-url`. |
| `forward-request` | Reduced | Endpoint configuration | Destination assets forward through their endpoint configuration. |

All other indexed statements are currently unsupported and carry either a
`warn` or `block` action. Unknown statement names are classified
deterministically: authentication, routing, and backend-critical names block;
all other names warn.

## Token-limit semantics

The destination shape is:

```json
{
  "type": "tokenLimit",
  "period": "minute",
  "count": 5000,
  "counterKey": "IPAddress"
}
```

Supported mappings:

- `tokens-per-minute` becomes `period: minute`.
- `token-quota` with `Hourly` becomes `period: hour`.
- `token-quota` with `Daily` becomes `period: day`.
- Exact IP-address expressions become `counterKey: IPAddress`.
- Exact APIM subscription/user/API-key identity expressions become
  `counterKey: Identity`. Subscription mappings warn that identity boundaries
  can differ.
- A source statement containing both rate and quota is split into two
  destination policies and produces a warning.

The following are not silently approximated:

- weekly, monthly, and yearly quotas
- nonliteral or nonpositive counts
- compound or arbitrary `counter-key` expressions
- prompt estimation
- retry, remaining-token, quota, and consumed-token headers or variables
- token policies outside the APIM `inbound` section

## Content-safety semantics

The destination shape is:

```json
{
  "type": "contentSafety",
  "hateSeverity": "Low",
  "selfHarmSeverity": "Low",
  "sexualSeverity": "Medium",
  "violenceSeverity": "High"
}
```

APIM threshold values are normalized using the portal-compatible mapping:

| APIM threshold | Destination severity |
| --- | --- |
| `0` through `2` | `Low` |
| `3` through `4` | `Medium` |
| `5` through `7` | `High` |

This covers APIM `FourSeverityLevels` outputs (`0`, `2`, `4`, `6`) and
`EightSeverityLevels` outputs (`0` through `7`). Expressions and values outside
that range are not translated.

The inline contract has no equivalent for `backend-id`, prompt shielding,
completion enforcement, windowing, or blocklists. These settings are named in
warnings and omitted. Inbound/outbound placement also becomes an asset-level
inline policy, so the inventory always requests review of request/response
enforcement behavior.

## Scope and control-flow rules

- Service and workspace policies are projected onto each destination asset.
  The inventory warns that inheritance boundaries and shared counters can
  change.
- API-scoped policies map directly to the destination asset.
- Operation- and product-scoped policies are fully inventoried but never
  promoted to asset scope.
- Policies nested under `choose`, `when`, or another structural element are not
  promoted unconditionally.
- Malformed policy XML blocks the affected asset assessment because its behavior
  cannot be inspected.

Translated objects are emitted under
`assets[].configuration.destinationPolicies`. Source policy summaries, scope,
recognized and unknown statements, and warnings remain under
`assets[].configuration.policies`.

## Security and output rules

Raw policy XML is not returned because policy attributes and element values can
contain credentials. Inventory output includes statement names, translated
objects, omitted field names, scope, and warnings without copying secret values.
Backend credentials and URL credentials/query values follow the same redaction
rule.

## Adding or expanding support

Every policy change must follow this sequence:

1. Add or update its `apim_policy_index.json` entry. Describe its source,
   applicability, destination capability, omitted behavior, and guidance.
2. Register exactly one handler with `_register_translator`. A handler returns
   `(destination_policies, warnings)` and must never silently default an
   unsupported value.
3. Preserve APIM control flow and scope. If the destination cannot represent
   either one, inventory the policy and emit a warning instead of broadening it.
4. Add tests for exact translation, every lossy field, expressions, invalid
   values, nested control flow, scope behavior, and value redaction.
5. Run `az ai-gateway policy import-support list|show` and verify that the
   published metadata matches executable behavior.
6. Update this document and `HISTORY.rst`.

The registry-consistency test prevents adding executable translation without
documented capability metadata, or documenting support without a registered
handler.
