Release History
===============

1.0.0b1
++++++++

* Initial Azure CLI extension scaffold.
* Added create, list, show, update, and delete commands for AI Gateway resources.
* Added create, list, show, update, and delete commands for model registrations.
* Added create, list, show, update, and delete commands for model aliases, with
  ETag-safe updates and deletes and per-command API-version overrides.
* Added create, list, show, update, and delete commands for model providers.
* Added default model synchronization when creating Foundry and custom model
  providers, with `--no-sync` to opt out.
* Added optional alias creation during model-provider creation and
  synchronization with `--aliases`.
* Added CRUD and OAuth authorization commands for MCP tool servers.
* Added API key lifecycle and managed identity commands.
* Added outbound VNet configuration and private endpoint connection management.
* Added create, list, and delete commands for Application Insights and custom
  OpenTelemetry monitoring exporters.
* Added inline policy CRUD across models, model aliases, and MCP tool servers.
* Added a stable, read-only, redacted APIM migration inventory command.
* Added BasicV2, StandardV2, and PremiumV2 capability-aware inventory with
  stable core discovery, preview MCP enrichment, collection coverage, retries,
  partial-page preservation, and platform-health diagnostics.
* Added APIM policy capability metadata and scoped-policy inventory.
* Added a queryable policy capability registry and compatibility guide.
