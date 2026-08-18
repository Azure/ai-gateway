# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------


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
        )
        group.custom_command("list", "list_gateways")
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
        group.custom_command("list", "list_models")
        group.custom_show_command("show", "show_model")
        group.custom_command("update", "update_model")

    with loader.command_group("ai-gateway mcp") as group:
        group.custom_command("authorize", "authorize_mcp")
        group.custom_command("create", "create_mcp")
        group.custom_command("delete", "delete_mcp", confirmation=True)
        group.custom_command("list", "list_mcp")
        group.custom_show_command("show", "show_mcp")
        group.custom_command("update", "update_mcp")

    with loader.command_group("ai-gateway api-key") as group:
        group.custom_command("create", "create_api_key")
        group.custom_command("delete", "delete_api_key", confirmation=True)
        group.custom_command("list", "list_api_keys")
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

    with loader.command_group("ai-gateway policy") as group:
        group.custom_command("create", "create_policy")
        group.custom_command("delete", "delete_policy", confirmation=True)
        group.custom_command("list", "list_policies")
        group.custom_show_command("show", "show_policy")
        group.custom_command("update", "update_policy")
