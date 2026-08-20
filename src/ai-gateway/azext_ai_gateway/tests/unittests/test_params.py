# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from collections import defaultdict
from unittest.mock import patch

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
    with patch.object(_params, "get_location_type", return_value=object()):
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
        "ai-gateway telemetry-exporter create",
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


def test_model_provider_create_no_sync_is_opt_out_flag():
    loader = _Loader()
    with patch.object(_params, "get_location_type", return_value=object()):
        _params.load_arguments(loader, None)

    argument = _get_argument(
        loader,
        "ai-gateway model-provider create",
        "no_sync",
    )

    assert argument["action"] == "store_true"


def test_model_provider_sync_accepts_api_key_value():
    loader = _Loader()
    with patch.object(_params, "get_location_type", return_value=object()):
        _params.load_arguments(loader, None)

    argument = _get_argument(
        loader,
        "ai-gateway model-provider sync",
        "api_key_value",
    )

    assert argument["arg_group"] == "Authentication"
    assert "prompts for it securely" in argument["help"]
    assert "sent exactly as entered" in argument["help"]


def test_telemetry_exporter_create_accepts_custom_otlp_options():
    loader = _Loader()
    with patch.object(_params, "get_location_type", return_value=object()):
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
