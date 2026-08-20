# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import AzureResponseError, HTTPError

from azext_ai_gateway import _private_endpoint_connection as private_endpoint


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


def _connection(status="Pending", provisioning_state="Succeeded"):
    return {
        "id": "/connections/connection",
        "name": "connection",
        "properties": {
            "privateEndpoint": {
                "id": (
                    "/subscriptions/sub/resourceGroups/network-rg/providers/"
                    "Microsoft.Network/privateEndpoints/gateway-pe"
                )
            },
            "privateLinkServiceConnectionState": {
                "status": status,
                "description": "description",
            },
            "provisioningState": provisioning_state,
        },
    }


@patch(
    "azext_ai_gateway._private_endpoint_connection.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._private_endpoint_connection._request")
def test_list_follows_pages(request, _, cmd):
    request.side_effect = [
        FakeResponse(
            {
                "value": [_connection()],
                "nextLink": "https://management.azure.com/next",
            }
        ),
        FakeResponse({"value": [_connection("Approved")]}),
    ]

    result = private_endpoint.list_private_endpoint_connections(
        cmd,
        "gateway",
        "rg",
    )

    assert len(result) == 2
    assert request.call_args_list[1] == call(
        cmd,
        "GET",
        "https://management.azure.com/next",
        include_api_version=False,
    )


def test_format_private_endpoint_connection_list_table():
    assert private_endpoint.format_private_endpoint_connection_list_table(
        [_connection()]
    ) == [
        {
            "Name": "connection",
            "Private endpoint": "gateway-pe",
            "Connection state": "Pending",
            "Provisioning state": "Succeeded",
            "Description": "description",
        }
    ]


@patch(
    "azext_ai_gateway._private_endpoint_connection.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._private_endpoint_connection._wait_for_connection")
@patch("azext_ai_gateway._private_endpoint_connection._request")
def test_approve_sends_status_and_waits(request, wait, _, cmd):
    request.return_value = FakeResponse(_connection("Pending", "Updating"))
    wait.return_value = _connection("Approved")

    result = private_endpoint.approve_private_endpoint_connection(
        cmd,
        "connection",
        "gateway",
        "rg",
        description="Reviewed",
    )

    body = request.call_args.args[3]
    assert body == {
        "properties": {
            "privateLinkServiceConnectionState": {
                "status": "Approved",
                "description": "Reviewed",
            }
        }
    }
    wait.assert_called_once_with(
        cmd,
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.ApiManagement/service/gateway/"
        "privateEndpointConnections/connection",
        "connection",
        expected_status="Approved",
    )
    assert result["properties"]["privateLinkServiceConnectionState"][
        "status"
    ] == "Approved"


@patch(
    "azext_ai_gateway._private_endpoint_connection.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._private_endpoint_connection._wait_for_connection")
@patch("azext_ai_gateway._private_endpoint_connection._request")
def test_reject_no_wait_returns_initial_response(request, wait, _, cmd):
    request.return_value = FakeResponse(_connection("Pending", "Updating"))

    result = private_endpoint.reject_private_endpoint_connection(
        cmd,
        "connection",
        "gateway",
        "rg",
        no_wait=True,
    )

    assert result["properties"]["provisioningState"] == "Updating"
    wait.assert_not_called()


@patch(
    "azext_ai_gateway._private_endpoint_connection.get_subscription_id",
    return_value="sub",
)
@patch("azext_ai_gateway._private_endpoint_connection._wait_for_connection")
@patch("azext_ai_gateway._private_endpoint_connection._request")
def test_delete_waits_for_connection_to_disappear(request, wait, _, cmd):
    request.return_value = FakeResponse()
    wait.return_value = None

    result = private_endpoint.delete_private_endpoint_connection(
        cmd,
        "connection",
        "gateway",
        "rg",
    )

    request.assert_called_once_with(
        cmd,
        "DELETE",
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.ApiManagement/service/gateway/"
        "privateEndpointConnections/connection",
    )
    wait.assert_called_once_with(
        cmd,
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.ApiManagement/service/gateway/"
        "privateEndpointConnections/connection",
        "connection",
        deleted=True,
    )
    assert result is None


@patch("azext_ai_gateway._private_endpoint_connection.time.sleep")
@patch("azext_ai_gateway._private_endpoint_connection._request")
def test_wait_fails_on_terminal_provisioning_failure(request, _, cmd):
    request.return_value = FakeResponse(_connection("Pending", "Failed"))

    with pytest.raises(AzureResponseError, match="state 'Failed'"):
        private_endpoint._wait_for_connection(
            cmd,
            "/connection",
            "connection",
            expected_status="Approved",
        )


@patch("azext_ai_gateway._private_endpoint_connection.time.sleep")
@patch("azext_ai_gateway._private_endpoint_connection._request")
def test_delete_wait_completes_on_not_found(request, _, cmd):
    request.side_effect = HTTPError(
        "Not Found",
        FakeResponse(status_code=404),
    )

    assert private_endpoint._wait_for_connection(
        cmd,
        "/connection",
        "connection",
        deleted=True,
    ) is None
