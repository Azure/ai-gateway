# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from collections import defaultdict

from azext_ai_gateway import _params


class _ArgumentContext:

    def __init__(self, command, arguments):
        self._command = command
        self._arguments = arguments

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def argument(self, name, *args, **kwargs):
        self._arguments[self._command].append((name, args, kwargs))

    def ignore(self, name):
        self._arguments[self._command].append((name, (), {"ignored": True}))


class _Loader:

    def __init__(self):
        self.cli_ctx = object()
        self.arguments = defaultdict(list)

    def argument_context(self, command):
        return _ArgumentContext(command, self.arguments)


def _get_argument(loader, command, name):
    matches = [
        argument
        for argument in loader.arguments[command]
        if argument[0] == name
    ]
    assert len(matches) == 1
    return matches[0][2]


def test_gateway_arguments_use_ai_gateway_configured_default():
    loader = _Loader()
    _params.load_arguments(loader, None)

    top_level_commands = [
        "ai-gateway create",
        "ai-gateway delete",
        "ai-gateway import",
        "ai-gateway show",
        "ai-gateway update",
    ]
    nested_commands = [
        *[
            f"ai-gateway model {operation}"
            for operation in ["create", "delete", "list", "show", "update"]
        ],
        *[
            f"ai-gateway model-provider {operation}"
            for operation in [
                "create",
                "delete",
                "list",
                "show",
                "sync",
                "update",
            ]
        ],
        *[
            f"ai-gateway mcp {operation}"
            for operation in [
                "authorize",
                "create",
                "delete",
                "list",
                "show",
                "test",
                "update",
            ]
        ],
        *[
            f"ai-gateway api-key {operation}"
            for operation in [
                "create",
                "delete",
                "list",
                "list-secrets",
                "regenerate",
                "show",
            ]
        ],
        *[
            f"ai-gateway identity {operation}"
            for operation in ["assign", "remove", "show"]
        ],
        *[
            f"ai-gateway telemetry-exporter {operation}"
            for operation in ["create", "delete", "list"]
        ],
        *[
            f"ai-gateway policy {operation}"
            for operation in ["create", "delete", "list", "show", "update"]
        ],
    ]

    for command in top_level_commands:
        argument = _get_argument(loader, command, "name")
        assert argument["configured_default"] == "ai-gateway"
        assert "az configure --defaults ai-gateway=<name>" in argument["help"]

    for command in nested_commands:
        argument = _get_argument(loader, command, "gateway_name")
        assert argument["configured_default"] == "ai-gateway"
        assert "az configure --defaults ai-gateway=<name>" in argument["help"]

    model_name = _get_argument(loader, "ai-gateway model create", "name")
    assert "configured_default" not in model_name


def test_gateway_create_accepts_list_regions_flag():
    loader = _Loader()
    _params.load_arguments(loader, None)

    argument = _get_argument(
        loader,
        "ai-gateway create",
        "list_regions",
    )
    assert argument["action"] == "store_true"


def test_gateway_show_accepts_managed_identity_selectors():
    loader = _Loader()
    _params.load_arguments(loader, None)

    for name in ["system_assigned", "user_assigned"]:
        argument = _get_argument(loader, "ai-gateway show", name)
        assert argument["action"] == "store_true"
        assert argument["arg_group"] == "Managed Identity"


def test_gateway_create_does_not_prevalidate_location():
    loader = _Loader()
    _params.load_arguments(loader, None)

    argument = _get_argument(loader, "ai-gateway create", "location")
    assert "arg_type" not in argument


def test_model_provider_create_no_sync_is_opt_out_flag():
    loader = _Loader()
    _params.load_arguments(loader, None)

    argument = _get_argument(
        loader,
        "ai-gateway model-provider create",
        "no_sync",
    )

    assert argument["action"] == "store_true"


def test_model_list_accepts_provider_and_type_filters():
    loader = _Loader()
    _params.load_arguments(loader, None)

    provider = _get_argument(
        loader,
        "ai-gateway model list",
        "provider_name",
    )
    model_type = _get_argument(
        loader,
        "ai-gateway model list",
        "model_type",
    )

    assert provider["options_list"] == [
        "--model-provider",
        "--provider-name",
    ]
    assert model_type["options_list"] == ["--type"]


def test_model_provider_sync_accepts_api_key_value():
    loader = _Loader()
    _params.load_arguments(loader, None)

    argument = _get_argument(
        loader,
        "ai-gateway model-provider sync",
        "api_key_value",
    )

    assert argument["arg_group"] == "Authentication"
    assert "prompts for it securely" in argument["help"]
    assert "sent exactly as entered" in argument["help"]


def test_mcp_test_accepts_api_key_name():
    loader = _Loader()
    _params.load_arguments(loader, None)

    argument = _get_argument(
        loader,
        "ai-gateway mcp test",
        "api_key_name",
    )

    assert argument["arg_group"] == "Authentication"
    assert argument["options_list"] == ["--api-key-name"]
    assert "resource" in argument["help"]


def test_telemetry_exporter_create_accepts_custom_otlp_options():
    loader = _Loader()
    _params.load_arguments(loader, None)

    command = "ai-gateway telemetry-exporter create"
    application_insights = _get_argument(
        loader,
        command,
        "application_insights",
    )
    assert application_insights["options_list"] == ["--application-insights"]

    name_argument = _get_argument(loader, command, "name")
    assert name_argument["options_list"] == ["--name", "-n"]

    for name in [
        "metrics_endpoint",
        "logs_endpoint",
        "traces_endpoint",
        "managed_identity_resource",
    ]:
        argument = _get_argument(
            loader,
            command,
            name,
        )
        assert argument["arg_group"] in {
            "Authentication",
            "Custom OpenTelemetry Destination",
        }

    headers = _get_argument(
        loader,
        command,
        "headers",
    )
    assert headers["type"] is _params.validate_headers

    for operation in ["create", "delete"]:
        name_argument = _get_argument(
            loader,
            f"ai-gateway telemetry-exporter {operation}",
            "name",
        )
        assert name_argument["required"] is True
        assert "default" not in name_argument



def test_workspace_name_is_not_exposed():
    loader = _Loader()
    _params.load_arguments(loader, None)

    commands = [
        *[
            f"ai-gateway model {operation}"
            for operation in ["create", "delete", "list", "show", "update"]
        ],
        *[
            f"ai-gateway model-provider {operation}"
            for operation in [
                "create",
                "delete",
                "list",
                "show",
                "sync",
                "update",
            ]
        ],
        *[
            f"ai-gateway mcp {operation}"
            for operation in [
                "authorize",
                "create",
                "delete",
                "list",
                "show",
                "update",
            ]
        ],
        *[
            f"ai-gateway telemetry-exporter {operation}"
            for operation in ["create", "delete", "list"]
        ],
        "ai-gateway policy create",
        "ai-gateway policy list",
    ]

    for command in commands:
        workspace = _get_argument(loader, command, "workspace_name")
        assert workspace["ignored"] is True


def test_policy_list_arguments_describe_scope_filters():
    loader = _Loader()
    _params.load_arguments(loader, None)

    command = "ai-gateway policy list"
    scope_type = _get_argument(loader, command, "scope_type")
    scope_name = _get_argument(loader, command, "scope_name")
    provider_name = _get_argument(loader, command, "provider_name")

    assert "Only include policies" in scope_type["help"]
    assert "--scope-type" in scope_name["help"]
    assert "--scope-type model and --scope-name" in provider_name["help"]


def test_telemetry_exporter_headers_allow_authorization():
    assert _params.validate_headers(
        '{"Authorization": "******"}'
    ) == {"Authorization": "******"}
