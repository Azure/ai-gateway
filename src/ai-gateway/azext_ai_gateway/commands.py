# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from azext_ai_gateway._import import format_import_table
from azext_ai_gateway._policy_translation import (
    format_policy_translation_table,
)
from azext_ai_gateway._model_provider import (
    format_model_provider_list_table,
    format_model_provider_sync_table,
)
from azext_ai_gateway._model import format_model_list_table
from azext_ai_gateway._mcp import format_mcp_list_table
from azext_ai_gateway._api_key import format_api_key_list_table
from azext_ai_gateway._policy import format_policy_list_table
from azext_ai_gateway._gateway import format_gateway_list_table
from azext_ai_gateway._private_endpoint_connection import (
    format_private_endpoint_connection_list_table,
)


def load_command_table(loader, _):
    with loader.command_group("ai-gateway") as group:
        group.custom_command(
            "create",
            "create_gateway",
            supports_no_wait=True,
        )
        group.custom_command(
            "delete",
            "delete_gateway",
            confirmation=True,
            supports_no_wait=True,
        )
        group.custom_command(
            "import",
            "import_from_apim",
            is_preview=True,
            supports_no_wait=True,
            table_transformer=format_import_table,
        )
        group.custom_command(
            "list",
            "list_gateways",
            table_transformer=format_gateway_list_table,
        )
        group.custom_show_command("show", "show_gateway")
        group.custom_command(
            "update",
            "update_gateway",
            supports_no_wait=True,
        )
        group.custom_command("version", "show_version")

    with loader.command_group("ai-gateway model") as group:
        group.custom_command("create", "create_model")
        group.custom_command("delete", "delete_model", confirmation=True)
        group.custom_command(
            "list",
            "list_models",
            table_transformer=format_model_list_table,
        )
        group.custom_show_command("show", "show_model")
        group.custom_command("update", "update_model")

    with loader.command_group("ai-gateway model-provider") as group:
        group.custom_command("create", "create_model_provider")
        group.custom_command(
            "delete",
            "delete_model_provider",
            confirmation=True,
        )
        group.custom_command(
            "list",
            "list_model_providers",
            table_transformer=format_model_provider_list_table,
        )
        group.custom_show_command("show", "show_model_provider")
        group.custom_command(
            "sync",
            "sync_model_provider",
            table_transformer=format_model_provider_sync_table,
        )
        group.custom_command("update", "update_model_provider")

    with loader.command_group("ai-gateway mcp") as group:
        group.custom_command("authorize", "authorize_mcp")
        group.custom_command("create", "create_mcp")
        group.custom_command("delete", "delete_mcp", confirmation=True)
        group.custom_command(
            "list",
            "list_mcp",
            table_transformer=format_mcp_list_table,
        )
        group.custom_show_command("show", "show_mcp")
        group.custom_command("update", "update_mcp")

    with loader.command_group("ai-gateway api-key") as group:
        group.custom_command("create", "create_api_key")
        group.custom_command("delete", "delete_api_key", confirmation=True)
        group.custom_command(
            "list",
            "list_api_keys",
            table_transformer=format_api_key_list_table,
        )
        group.custom_command("list-secrets", "list_api_key_secrets")
        group.custom_command(
            "regenerate",
            "regenerate_api_key",
            confirmation=True,
        )
        group.custom_show_command("show", "show_api_key")

    with loader.command_group("ai-gateway identity") as group:
        group.custom_command(
            "assign",
            "assign_identity",
            supports_no_wait=True,
        )
        group.custom_command(
            "remove",
            "remove_identity",
            confirmation=True,
            supports_no_wait=True,
        )
        group.custom_show_command("show", "show_identity")

    with loader.command_group(
        "ai-gateway private-endpoint"
    ) as group:
        group.custom_command(
            "approve",
            "approve_private_endpoint_connection",
            supports_no_wait=True,
        )
        group.custom_command(
            "delete",
            "delete_private_endpoint_connection",
            confirmation=True,
            supports_no_wait=True,
        )
        group.custom_command(
            "list",
            "list_private_endpoint_connections",
            table_transformer=format_private_endpoint_connection_list_table,
        )
        group.custom_command(
            "reject",
            "reject_private_endpoint_connection",
            supports_no_wait=True,
        )
        group.custom_show_command(
            "show",
            "show_private_endpoint_connection",
        )

    with loader.command_group("ai-gateway telemetry-exporter") as group:
        group.custom_command("create", "create_telemetry_exporter")
        group.custom_command(
            "delete",
            "delete_telemetry_exporter",
            confirmation=True,
        )
        group.custom_command("list", "list_telemetry_exporters")

    with loader.command_group("ai-gateway policy") as group:
        group.custom_command("create", "create_policy")
        group.custom_command("delete", "delete_policy", confirmation=True)
        group.custom_command(
            "list",
            "list_policies",
            table_transformer=format_policy_list_table,
        )
        group.custom_show_command("show", "show_policy")
        group.custom_command("update", "update_policy")

    with loader.command_group("ai-gateway policy import-support") as group:
        group.custom_command(
            "list",
            "list_policy_translation_support",
            table_transformer=format_policy_translation_table,
        )
        group.custom_show_command(
            "show",
            "show_policy_translation_support",
            table_transformer=format_policy_translation_table,
        )
