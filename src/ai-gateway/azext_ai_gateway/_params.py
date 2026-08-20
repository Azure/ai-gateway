# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from azure.cli.core.commands.parameters import (
    file_type,
    get_enum_type,
    get_three_state_flag,
    resource_group_name_type,
    tags_type,
)

from azext_ai_gateway._validators import (
    validate_endpoints,
    validate_headers,
    validate_policies,
    validate_policy,
)

AI_GATEWAY_CONFIGURED_DEFAULT = "ai-gateway"
AI_GATEWAY_DEFAULT_HELP = (
    " You can configure the default using "
    "`az configure --defaults ai-gateway=<name>`."
)


def load_arguments(loader, _):
    for command in [
        "ai-gateway create",
        "ai-gateway delete",
        "ai-gateway show",
        "ai-gateway update",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "name",
                options_list=["--name", "-n"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)

    with loader.argument_context("ai-gateway create") as context:
        context.argument(
            "list_regions",
            action="store_true",
            help=(
                "List the Azure regions supported by the AI Gateway SKU "
                "without creating a gateway."
            ),
        )
        context.argument(
            "location",
            options_list=["--location", "-l"],
            help=(
                "Azure region in which to create the gateway. The value is "
                "sent directly to the AI Gateway service for validation."
            ),
        )
        context.argument(
            "publisher_email",
            help="Publisher email used by the underlying API Management service.",
        )
        context.argument(
            "publisher_name",
            help="Publisher name used by the underlying API Management service.",
        )

    with loader.argument_context("ai-gateway list") as context:
        context.argument(
            "resource_group_name",
            resource_group_name_type,
            required=False,
        )

    with loader.argument_context("ai-gateway show") as context:
        context.argument(
            "system_assigned",
            action="store_true",
            arg_group="Managed Identity",
            help="Show only the system-assigned managed identity details.",
        )
        context.argument(
            "user_assigned",
            action="store_true",
            arg_group="Managed Identity",
            help="Show only the user-assigned managed identity details.",
        )

    for command in ["ai-gateway create", "ai-gateway update"]:
        with loader.argument_context(command) as context:
            context.argument("tags", tags_type)
            context.argument(
                "mi_system_assigned",
                options_list=["--mi-system-assigned"],
                arg_type=get_three_state_flag(),
                arg_group="Managed Identity",
                help="Enable or disable the system-assigned managed identity.",
            )
            context.argument(
                "mi_user_assigned",
                options_list=["--mi-user-assigned"],
                nargs="*",
                arg_group="Managed Identity",
                help=(
                    "Space-separated user-assigned managed identity resource IDs. "
                    "Pass the option without values on update to remove all."
                ),
            )

    with loader.argument_context("ai-gateway update") as context:
        context.argument(
            "public_network_access",
            arg_type=get_enum_type(["Enabled", "Disabled"]),
            arg_group="Networking",
            help="Allow or deny public network access.",
        )
        context.argument(
            "virtual_network_type",
            arg_type=get_enum_type(["None", "External"]),
            arg_group="Networking",
            help="Outbound virtual network integration mode.",
        )
        context.argument(
            "subnet_resource_id",
            arg_group="Networking",
            help=(
                "Resource ID of the delegated integration subnet. "
                "A non-empty value enables External integration. Set "
                "--virtual-network-type None to clear the configuration."
            ),
        )

    private_endpoint_connection_commands = [
        "ai-gateway private-endpoint approve",
        "ai-gateway private-endpoint delete",
        "ai-gateway private-endpoint list",
        "ai-gateway private-endpoint reject",
        "ai-gateway private-endpoint show",
    ]
    for command in private_endpoint_connection_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the parent AI Gateway."
                + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)

    for command in [
        "ai-gateway private-endpoint approve",
        "ai-gateway private-endpoint delete",
        "ai-gateway private-endpoint reject",
        "ai-gateway private-endpoint show",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "name",
                options_list=["--name", "-n"],
                help="Name of the private endpoint connection.",
            )

    for command in [
        "ai-gateway private-endpoint approve",
        "ai-gateway private-endpoint reject",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "description",
                help="Reason for approving or rejecting the connection.",
            )

    model_commands = [
        "ai-gateway model create",
        "ai-gateway model delete",
        "ai-gateway model list",
        "ai-gateway model show",
        "ai-gateway model update",
    ]
    for command in model_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the parent AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)
            context.ignore("workspace_name")

    for command in [
        "ai-gateway model create",
        "ai-gateway model delete",
        "ai-gateway model show",
        "ai-gateway model update",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "name",
                options_list=["--name", "-n"],
                help="Name of the model registration.",
            )
            context.argument(
                "provider_name",
                help="Name of the parent model provider.",
            )

    with loader.argument_context("ai-gateway model list") as context:
        context.argument(
            "provider_name",
            options_list=["--model-provider", "--provider-name"],
            required=False,
            help="Only list models belonging to this provider.",
        )
        context.argument(
            "model_type",
            options_list=["--type"],
            arg_type=get_enum_type(["Foundry", "Custom"]),
            help="Only list models with this provider type.",
        )

    for command in [
        "ai-gateway model create",
        "ai-gateway model update",
    ]:
        with loader.argument_context(command) as context:
            context.argument("display_name", help="Display name of the model.")
            context.argument("description", help="Description of the model.")
            context.argument(
                "api_format",
                arg_type=get_enum_type(
                    [
                        "OpenAIChatCompletions",
                        "AnthropicMessages",
                        "ResponsesApi",
                    ]
                ),
                help="API format exposed by the model.",
            )
            context.argument(
                "deployment_resource_id",
                arg_group="Deployment",
                help="Resource ID of the backing Foundry deployment.",
            )
            context.argument(
                "deployment_model_name",
                arg_group="Deployment",
                help="Model name reported by the backing deployment.",
            )
            context.argument(
                "deployment_model_version",
                arg_group="Deployment",
                help="Model version reported by the backing deployment.",
            )
            context.argument(
                "supported_endpoints",
                nargs="+",
                help="Space-separated data-plane endpoint paths.",
            )
            context.argument(
                "policies",
                type=validate_policies,
                help="Inline policy JSON array or path prefixed with '@'.",
            )

    with loader.argument_context("ai-gateway model update") as context:
        context.argument(
            "if_match",
            help=(
                "ETag used to reject stale updates. By default, the current "
                "ETag is retrieved automatically."
            ),
        )

    model_provider_commands = [
        "ai-gateway model-provider create",
        "ai-gateway model-provider delete",
        "ai-gateway model-provider list",
        "ai-gateway model-provider show",
        "ai-gateway model-provider sync",
        "ai-gateway model-provider update",
    ]
    for command in model_provider_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the parent AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)
            context.ignore("workspace_name")

    for command in [
        "ai-gateway model-provider create",
        "ai-gateway model-provider delete",
        "ai-gateway model-provider show",
        "ai-gateway model-provider sync",
        "ai-gateway model-provider update",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "name",
                options_list=["--name", "-n"],
                help="Name of the model provider.",
            )

    for command in [
        "ai-gateway model-provider create",
        "ai-gateway model-provider update",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "display_name",
                help="Display name of the model provider.",
            )
            context.argument(
                "description",
                help="Description of the model provider.",
            )
            context.argument(
                "endpoint",
                arg_group="Provider",
                help="Provider endpoint URL.",
            )
            context.argument(
                "resource_ids",
                nargs="+",
                arg_group="Provider",
                help=(
                    "One or more space-separated Foundry resource IDs "
                    "available through this provider."
                ),
            )
            context.argument(
                "auth_kind",
                arg_type=get_enum_type(["ManagedIdentity", "ApiKey"]),
                arg_group="Authentication",
                help=(
                    "Authentication kind. Defaults to ManagedIdentity for "
                    "Foundry and ApiKey for Custom."
                ),
            )
            context.argument(
                "api_key_header_name",
                arg_group="Authentication",
                help="HTTP header carrying the provider API key.",
            )
            context.argument(
                "api_key_value",
                arg_group="Authentication",
                help="Provider API key value.",
            )
            context.argument(
                "managed_identity_resource",
                arg_group="Authentication",
                help=(
                    "Token audience for managed identity authentication. "
                    "Defaults to https://cognitiveservices.azure.com."
                ),
            )
            context.argument(
                "managed_identity_client_id",
                arg_group="Authentication",
                help="Client ID of a user-assigned managed identity.",
            )

    with loader.argument_context(
        "ai-gateway model-provider create"
    ) as context:
        context.argument(
            "kind",
            arg_type=get_enum_type(["Foundry", "Custom"]),
            help="Model provider kind.",
        )
        context.argument(
            "no_sync",
            action="store_true",
            help=(
                "Create the model provider without discovering and importing "
                "its models."
            ),
        )

    with loader.argument_context(
        "ai-gateway model-provider sync"
    ) as context:
        context.argument(
            "api_key_value",
            arg_group="Authentication",
            help=(
                "Provider API key value. When omitted for a custom provider, "
                "an interactive terminal prompts for it securely. The value "
                "is sent exactly as entered; include an authentication scheme "
                "only when the provider requires one."
            ),
        )
        context.argument(
            "dry_run",
            action="store_true",
            help="Return the synchronization plan without changing models.",
        )
        context.argument(
            "yes",
            options_list=["--yes", "-y"],
            action="store_true",
            help="Confirm model creation and deletion.",
        )

    mcp_commands = [
        "ai-gateway mcp authorize",
        "ai-gateway mcp create",
        "ai-gateway mcp delete",
        "ai-gateway mcp list",
        "ai-gateway mcp show",
        "ai-gateway mcp test",
        "ai-gateway mcp update",
    ]
    for command in mcp_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the parent AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)
            context.ignore("workspace_name")

    for command in [
        "ai-gateway mcp authorize",
        "ai-gateway mcp create",
        "ai-gateway mcp delete",
        "ai-gateway mcp show",
        "ai-gateway mcp test",
        "ai-gateway mcp update",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "name",
                options_list=["--name", "-n"],
                help="Name of the MCP tool server.",
            )

    for command in ["ai-gateway mcp create", "ai-gateway mcp update"]:
        with loader.argument_context(command) as context:
            context.argument(
                "endpoints",
                type=validate_endpoints,
                help=(
                    "Non-empty endpoint JSON array or path prefixed with '@'. "
                    "Use a file when the definition contains secrets."
                ),
            )
            context.argument(
                "display_name",
                help="Display name of the MCP tool server.",
            )
            context.argument(
                "description",
                help="Description of the MCP tool server.",
            )
            context.argument(
                "failure_mode",
                arg_type=get_enum_type(["failOpen", "failClosed"]),
                help="Behavior when one or more endpoints are unavailable.",
            )
            context.argument(
                "policies",
                type=validate_policies,
                help="Inline policy JSON array or path prefixed with '@'.",
            )

    with loader.argument_context("ai-gateway mcp update") as context:
        context.argument(
            "if_match",
            help=(
                "ETag used to reject stale updates. By default, the current "
                "ETag is retrieved automatically."
            ),
        )

    with loader.argument_context("ai-gateway mcp authorize") as context:
        context.argument(
            "endpoint_id",
            help="Server-generated ID of the OAuth endpoint.",
        )

    with loader.argument_context("ai-gateway mcp test") as context:
        context.argument(
            "api_key_name",
            options_list=["--api-key-name"],
            arg_group="Authentication",
            help="Name of the AI Gateway API key resource to use.",
        )

    api_key_commands = [
        "ai-gateway api-key create",
        "ai-gateway api-key delete",
        "ai-gateway api-key list",
        "ai-gateway api-key list-secrets",
        "ai-gateway api-key regenerate",
        "ai-gateway api-key show",
    ]
    for command in api_key_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the parent AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)

    for command in [
        "ai-gateway api-key create",
        "ai-gateway api-key delete",
        "ai-gateway api-key list-secrets",
        "ai-gateway api-key regenerate",
        "ai-gateway api-key show",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "name",
                options_list=["--name", "-n"],
                help="Name of the API key resource.",
            )

    with loader.argument_context("ai-gateway api-key create") as context:
        context.argument(
            "display_name",
            help="Human-readable API key name. Defaults to the resource name.",
        )

    with loader.argument_context("ai-gateway api-key regenerate") as context:
        context.argument(
            "key_type",
            arg_type=get_enum_type(["primary", "secondary"]),
            help="Key value to regenerate.",
        )

    identity_commands = [
        "ai-gateway identity assign",
        "ai-gateway identity remove",
        "ai-gateway identity show",
    ]
    for command in identity_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)

    for command in [
        "ai-gateway identity assign",
        "ai-gateway identity remove",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "system_assigned",
                action="store_true",
                help="Assign or remove the system-assigned managed identity.",
            )

    with loader.argument_context("ai-gateway identity assign") as context:
        context.argument(
            "user_assigned",
            nargs="+",
            help="User-assigned managed identity resource IDs to attach.",
        )

    with loader.argument_context("ai-gateway identity remove") as context:
        context.argument(
            "user_assigned",
            nargs="*",
            help=(
                "User-assigned managed identity resource IDs to detach. "
                "Pass the option without values to detach all."
            ),
        )

    telemetry_exporter_commands = [
        "ai-gateway telemetry-exporter create",
        "ai-gateway telemetry-exporter delete",
        "ai-gateway telemetry-exporter list",
    ]
    for command in telemetry_exporter_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)
            context.ignore("workspace_name")

    for command in [
        "ai-gateway telemetry-exporter create",
        "ai-gateway telemetry-exporter delete",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "name",
                options_list=["--name", "-n"],
                required=True,
                help="Telemetry exporter name.",
            )

    with loader.argument_context("ai-gateway telemetry-exporter create") as context:
        context.argument(
            "application_insights",
            options_list=["--application-insights"],
            help="Resource ID of an existing Application Insights component.",
        )
        context.argument(
            "identity_client_id",
            arg_group="Authentication",
            help=(
                "Client ID of an assigned user-assigned managed identity. By "
                "default, the system-assigned identity or first available "
                "identity is used."
            ),
        )
        context.argument(
            "metrics_endpoint",
            arg_group="Custom OpenTelemetry Destination",
            help=(
                "Absolute HTTPS OTLP metrics endpoint URL. At least one signal "
                "endpoint is required."
            ),
        )
        context.argument(
            "logs_endpoint",
            arg_group="Custom OpenTelemetry Destination",
            help="Absolute HTTPS OTLP logs endpoint URL.",
        )
        context.argument(
            "traces_endpoint",
            arg_group="Custom OpenTelemetry Destination",
            help="Absolute HTTPS OTLP traces endpoint URL.",
        )
        context.argument(
            "headers",
            type=validate_headers,
            arg_group="Authentication",
            help=(
                "Optional custom OTLP headers as a JSON object or path "
                "prefixed with '@'."
            ),
        )
        context.argument(
            "managed_identity_resource",
            arg_group="Authentication",
            help=(
                "Token audience URL for custom OTLP managed identity "
                "authentication."
            ),
        )
        context.argument(
            "payload_capture",
            action="store_true",
            help=(
                "Capture request and response payloads in exported telemetry. "
                "Payloads may contain sensitive or regulated data."
            ),
        )

    policy_commands = [
        "ai-gateway policy create",
        "ai-gateway policy delete",
        "ai-gateway policy list",
        "ai-gateway policy show",
        "ai-gateway policy update",
    ]
    for command in policy_commands:
        with loader.argument_context(command) as context:
            context.argument(
                "gateway_name",
                options_list=["--resource-name"],
                configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
                help="Name of the parent AI Gateway." + AI_GATEWAY_DEFAULT_HELP,
            )
            context.argument("resource_group_name", resource_group_name_type)

    for command in [
        "ai-gateway policy delete",
        "ai-gateway policy show",
        "ai-gateway policy update",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "policy_id",
                options_list=["--policy-id"],
                help="Synthesized policy ID returned by policy list or create.",
            )

    for command in [
        "ai-gateway policy create",
        "ai-gateway policy update",
    ]:
        with loader.argument_context(command) as context:
            context.argument(
                "policy",
                type=validate_policy,
                help="Policy JSON object or path prefixed with '@'.",
            )

    for command in ["ai-gateway policy create", "ai-gateway policy list"]:
        with loader.argument_context(command) as context:
            context.ignore("workspace_name")

    with loader.argument_context("ai-gateway policy create") as context:
        context.argument(
            "scope_type",
            arg_type=get_enum_type(["model", "mcp"]),
            help="Type of resource that hosts the inline policy.",
        )
        context.argument(
            "scope_name",
            help="Name of the model or MCP tool server.",
        )
        context.argument(
            "provider_name",
            help="Model provider name. Required for a model target.",
        )

    with loader.argument_context("ai-gateway policy list") as context:
        context.argument(
            "scope_type",
            arg_type=get_enum_type(["model", "mcp"]),
            help="Only include policies attached to this resource type.",
        )
        context.argument(
            "scope_name",
            help=(
                "Only include policies attached to this model or MCP tool "
                "server. Requires --scope-type."
            ),
        )
        context.argument(
            "provider_name",
            help=(
                "Only include model policies for this provider. Required with "
                "--scope-type model and --scope-name."
            ),
        )

    with loader.argument_context(
        "ai-gateway policy import-support list"
    ) as context:
        context.argument(
            "support_level",
            arg_type=get_enum_type(["partial", "consumed", "unsupported"]),
            help="Only list capabilities at this support level.",
        )

    with loader.argument_context(
        "ai-gateway policy import-support show"
    ) as context:
        context.argument(
            "name",
            options_list=["--name", "-n"],
            help="Source APIM policy statement name.",
        )

    with loader.argument_context("ai-gateway import") as context:
        context.argument(
            "name",
            options_list=["--name", "-n"],
            configured_default=AI_GATEWAY_CONFIGURED_DEFAULT,
            help=(
                "Name of the destination AI Gateway."
                + AI_GATEWAY_DEFAULT_HELP
            ),
        )
        context.argument(
            "resource_group_name",
            resource_group_name_type,
        )
        context.argument(
            "source_apim_id",
            options_list=["--source-apim-id"],
            help="Resource ID of the source Azure API Management service.",
        )
        context.argument(
            "include",
            nargs="+",
            arg_type=get_enum_type(["models", "agents", "tools"]),
            default=["models", "agents", "tools"],
            help="Configuration types to import.",
        )
        context.argument(
            "conflict_policy",
            arg_type=get_enum_type(["fail", "skip", "overwrite"]),
            default="fail",
            help="Action to take when a destination resource already exists.",
        )
        context.argument(
            "mapping_file",
            type=file_type,
            help=(
                "Path to a JSON file containing models, agents, and tools "
                "source-to-destination mappings."
            ),
        )
        context.argument(
            "dry_run",
            action="store_true",
            help=(
                "Discover assets and display a compatibility inventory without "
                "changing either resource. Currently required."
            ),
        )
