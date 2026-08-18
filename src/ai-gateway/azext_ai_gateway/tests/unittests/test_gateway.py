# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import (
    AzureResponseError,
    HTTPError,
    RequiredArgumentMissingError,
)

from azext_ai_gateway import _gateway


class FakeResponse:

    def __init__(self, body=None, status_code=200):
        self._body = body
        self.status_code = status_code
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


@pytest.fixture
def cmd():
    return SimpleNamespace(cli_ctx=object())


@patch("azext_ai_gateway._gateway.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_uses_fixed_sku_and_defaults(
    send_request,
    wait_for_gateway,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"properties": {"provisioningState": "Creating"}}
    )
    wait_for_gateway.return_value = {
        "properties": {"provisioningState": "Succeeded"}
    }

    result = _gateway.create_gateway(cmd, "gateway", "rg", "eastus2")

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {
        "location": "eastus2",
        "sku": {"name": "AIGateway", "capacity": 1},
        "properties": {
            "publisherEmail": _gateway.DEFAULT_PUBLISHER_EMAIL,
            "publisherName": _gateway.DEFAULT_PUBLISHER_NAME,
        },
    }
    assert result["properties"]["provisioningState"] == "Succeeded"


@patch("azext_ai_gateway._gateway.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_list_follows_pages_and_filters_non_ai_gateway_skus(
    send_request,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "value": [
                    {"name": "ai-one", "sku": {"name": "AIGateway"}},
                    {"name": "classic", "sku": {"name": "Developer"}},
                ],
                "nextLink": "https://management.azure.com/next-page",
            }
        ),
        FakeResponse(
            {"value": [{"name": "ai-two", "sku": {"name": "aigateway"}}]}
        ),
    ]

    result = _gateway.list_gateways(cmd)

    assert [gateway["name"] for gateway in result] == ["ai-one", "ai-two"]
    assert send_request.call_count == 2
    assert send_request.call_args_list[1] == call(
        cmd.cli_ctx,
        "GET",
        "https://management.azure.com/next-page",
        uri_parameters=None,
        body=None,
    )


@patch("azext_ai_gateway._gateway.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_sends_only_supplied_networking_properties(
    send_request,
    wait_for_gateway,
    _,
    cmd,
):
    send_request.return_value = FakeResponse(
        {"properties": {"provisioningState": "Updating"}}
    )
    wait_for_gateway.return_value = {
        "properties": {"provisioningState": "Succeeded"}
    }

    _gateway.update_gateway(
        cmd,
        "gateway",
        "rg",
        public_network_access="Disabled",
        subnet_resource_id="",
    )

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {
        "properties": {
            "publicNetworkAccess": "Disabled",
            "virtualNetworkConfiguration": None,
        }
    }


def test_update_requires_at_least_one_property(cmd):
    with pytest.raises(RequiredArgumentMissingError):
        _gateway.update_gateway(cmd, "gateway", "rg")


@patch("azext_ai_gateway._gateway.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_preserves_unspecified_user_assigned_identities(
    send_request,
    wait_for_gateway,
    _,
    cmd,
):
    identity_id = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.ManagedIdentity/userAssignedIdentities/existing"
    )
    send_request.side_effect = [
        FakeResponse(
            {
                "identity": {
                    "type": "UserAssigned",
                    "userAssignedIdentities": {identity_id: {}},
                }
            }
        ),
        FakeResponse({"properties": {"provisioningState": "Updating"}}),
    ]
    wait_for_gateway.return_value = {
        "properties": {"provisioningState": "Succeeded"}
    }

    _gateway.update_gateway(
        cmd,
        "gateway",
        "rg",
        mi_system_assigned=True,
    )

    body = json.loads(send_request.call_args_list[1].kwargs["body"])
    assert body["identity"] == {
        "type": "SystemAssigned, UserAssigned",
        "userAssignedIdentities": {identity_id: {}},
    }


@patch("azext_ai_gateway._gateway.time.sleep")
@patch("azext_ai_gateway._gateway._get_resource")
def test_wait_fails_on_terminal_failure(get_resource, _, cmd):
    get_resource.return_value = {
        "properties": {"provisioningState": "Failed"}
    }

    with pytest.raises(AzureResponseError, match="state 'Failed'"):
        _gateway._wait_for_gateway(cmd, "/gateway", "gateway")


@patch("azext_ai_gateway._gateway.time.sleep")
@patch("azext_ai_gateway._gateway._get_resource")
def test_delete_wait_completes_when_resource_is_not_found(get_resource, _, cmd):
    get_resource.side_effect = HTTPError(
        "Not Found",
        FakeResponse(status_code=404),
    )

    assert _gateway._wait_for_gateway(
        cmd,
        "/gateway",
        "gateway",
        deleted=True,
    ) is None


@patch("azext_ai_gateway._gateway.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_delete_waits_for_resource_to_disappear(
    send_request,
    wait_for_gateway,
    _,
    cmd,
):
    send_request.return_value = FakeResponse()
    wait_for_gateway.return_value = None

    assert _gateway.delete_gateway(cmd, "gateway", "rg") is None
    wait_for_gateway.assert_called_once_with(
        cmd,
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.ApiManagement/service/gateway",
        "gateway",
        deleted=True,
    )
