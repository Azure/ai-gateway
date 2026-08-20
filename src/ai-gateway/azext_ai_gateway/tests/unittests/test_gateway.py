# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
import logging
from types import SimpleNamespace
from unittest.mock import call, patch

import pytest
from azure.cli.core.azclierror import (
    AzureResponseError,
    HTTPError,
    InvalidArgumentValueError,
    RequiredArgumentMissingError,
)
from requests import Response

from azext_ai_gateway import _gateway


class FakeResponse:

    def __init__(self, body=None, status_code=200, reason=None):
        self._body = body
        self.status_code = status_code
        self.reason = reason
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


@pytest.fixture
def cmd():
    return SimpleNamespace(cli_ctx=object())


def test_response_json_accepts_utf8_bom():
    response = Response()
    response._content = json.dumps(
        {"properties": {"value": "policy"}}
    ).encode("utf-8-sig")
    response.encoding = "utf-8"

    assert _gateway._response_json(response) == {
        "properties": {"value": "policy"}
    }


def test_request_suppresses_raw_http_debug_logs(cmd, caplog):
    logger = logging.getLogger(__name__)

    def send_request(*args, **kwargs):
        del args, kwargs
        logger.debug("request body contains sentinel-secret")
        logger.debug("response body contains sentinel-secret")
        return FakeResponse({})

    caplog.set_level(logging.DEBUG, logger=__name__)
    with patch.object(_gateway, "send_raw_request", send_request):
        _gateway._request(
            cmd,
            "POST",
            "/resource",
            {"credentials": {"secret": "sentinel-secret"}},
        )

    assert "sentinel-secret" not in caplog.text


@patch("azext_ai_gateway._gateway.send_raw_request")
def test_sensitive_request_error_does_not_expose_response_body(
    send_request,
    cmd,
):
    response = FakeResponse(
        {
            "error": {
                "code": "InvalidCredentials",
                "message": "rejected sentinel-secret",
            }
        },
        status_code=400,
        reason="Bad Request",
    )
    send_request.side_effect = HTTPError(
        "Bad Request(rejected sentinel-secret)",
        response,
    )

    with pytest.raises(HTTPError) as error:
        _gateway._request(
            cmd,
            "PUT",
            "/resource",
            {"properties": {"clientSecret": "sentinel-secret"}},
        )

    assert str(error.value) == (
        "PUT request failed with HTTP 400: Bad Request. "
        "Code: InvalidCredentials."
    )
    assert error.value.response is response


@patch("azext_ai_gateway._gateway.send_raw_request")
def test_request_error_includes_service_code_and_description(
    send_request,
    cmd,
):
    response = FakeResponse(
        {
            "error": {
                "code": "InvalidPolicy",
                "message": "periodSeconds is required.",
            }
        },
        status_code=400,
        reason="Bad Request",
    )
    send_request.side_effect = HTTPError("Bad Request", response)

    with pytest.raises(HTTPError) as error:
        _gateway._request(
            cmd,
            "PATCH",
            "/resource",
            {"properties": {"policies": []}},
        )

    assert str(error.value) == (
        "PATCH request failed with HTTP 400: Bad Request. "
        "Code: InvalidPolicy. Description: periodSeconds is required."
    )
    assert error.value.response is response


@patch("azext_ai_gateway._gateway.send_raw_request")
def test_request_error_handles_non_json_response(send_request, cmd):
    response = FakeResponse(status_code=502, reason="Bad Gateway")
    send_request.side_effect = HTTPError("Bad Gateway", response)

    with pytest.raises(HTTPError) as error:
        _gateway._request(cmd, "GET", "/resource")

    assert str(error.value) == "GET request failed with HTTP 502: Bad Gateway."


@patch("azext_ai_gateway._gateway.send_raw_request")
def test_sensitive_request_omits_free_form_error_code(send_request, cmd):
    response = FakeResponse(
        {
            "error": {
                "code": "Invalid sentinel-secret",
                "message": "rejected sentinel-secret",
            }
        },
        status_code=400,
        reason="Bad Request",
    )
    send_request.side_effect = HTTPError("Bad Request", response)

    with pytest.raises(HTTPError) as error:
        _gateway._request(
            cmd,
            "PUT",
            "/resource",
            {"credentials": {"secret": "sentinel-secret"}},
        )

    assert str(error.value) == "PUT request failed with HTTP 400: Bad Request."


def test_list_secrets_request_is_always_sensitive():
    assert _gateway._is_sensitive_request(
        "/resources/key/listSecrets",
        None,
    )


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


@patch("azext_ai_gateway._gateway.get_subscription_id")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_create_list_regions_does_not_require_creation_arguments(
    send_request,
    get_subscription,
    cmd,
):
    assert _gateway.create_gateway(cmd, list_regions=True) == [
        {"name": "eastus2", "displayName": "East US 2"},
        {"name": "swedencentral", "displayName": "Sweden Central"},
    ]
    get_subscription.assert_not_called()
    send_request.assert_not_called()


@pytest.mark.parametrize(
    ("kwargs", "missing_option"),
    [
        (
            {"resource_group_name": "rg", "location": "eastus2"},
            "--name",
        ),
        (
            {"name": "gateway", "location": "eastus2"},
            "--resource-group",
        ),
        (
            {"name": "gateway", "resource_group_name": "rg"},
            "--location",
        ),
    ],
)
def test_create_requires_creation_arguments_without_list_regions(
    cmd,
    kwargs,
    missing_option,
):
    with pytest.raises(RequiredArgumentMissingError, match=missing_option):
        _gateway.create_gateway(cmd, **kwargs)


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


def test_format_gateway_list_table():
    gateways = [
        {
            "id": (
                "/subscriptions/sub/resourceGroups/ai-gateway-contoso-aigw/"
                "providers/Microsoft.ApiManagement/service/contoso-aigw"
            ),
            "name": "contoso-aigw",
            "location": "East US 2",
            "properties": {
                "gatewayUrl": (
                    "https://contoso-aigw.eastus2.ai.gateway.azure.com"
                )
            },
        },
        {
            "id": (
                "/subscriptions/sub/RESOURCEGROUPS/encoded%20group/"
                "providers/Microsoft.ApiManagement/service/other-aigw"
            ),
            "name": "other-aigw",
            "location": "West US 2",
        },
    ]

    assert _gateway.format_gateway_list_table(gateways) == [
        {
            "Name": "contoso-aigw",
            "ResourceGroup": "ai-gateway-contoso-aigw",
            "Location": "East US 2",
            "Runtime URL": (
                "https://contoso-aigw.eastus2.ai.gateway.azure.com"
            ),
        },
        {
            "Name": "other-aigw",
            "ResourceGroup": "encoded group",
            "Location": "West US 2",
            "Runtime URL": "",
        },
    ]


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
        virtual_network_type="None",
    )

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {
        "properties": {
            "publicNetworkAccess": "Disabled",
            "virtualNetworkType": "None",
            "virtualNetworkConfiguration": None,
        }
    }


@patch("azext_ai_gateway._gateway.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_infers_external_from_subnet(
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
    subnet_id = (
        "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.Network/virtualNetworks/vnet/subnets/integration"
    )

    _gateway.update_gateway(
        cmd,
        "gateway",
        "rg",
        subnet_resource_id=subnet_id,
    )

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {
        "properties": {
            "virtualNetworkType": "External",
            "virtualNetworkConfiguration": {
                "subnetResourceId": subnet_id,
            },
        }
    }


@patch("azext_ai_gateway._gateway.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._gateway._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_update_public_access_does_not_overwrite_vnet_configuration(
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
    )

    body = json.loads(send_request.call_args.kwargs["body"])
    assert body == {"properties": {"publicNetworkAccess": "Disabled"}}


@pytest.mark.parametrize(
    ("virtual_network_type", "subnet_resource_id", "message"),
    [
        ("External", None, "--subnet-resource-id is required"),
        (
            "None",
            "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.Network/virtualNetworks/vnet/subnets/integration",
            "cannot be combined",
        ),
        ("External", "not-a-resource-id", "full Microsoft.Network"),
    ],
)
def test_update_rejects_invalid_networking_combinations(
    cmd,
    virtual_network_type,
    subnet_resource_id,
    message,
):
    with pytest.raises(InvalidArgumentValueError, match=message):
        _gateway.update_gateway(
            cmd,
            "gateway",
            "rg",
            virtual_network_type=virtual_network_type,
            subnet_resource_id=subnet_resource_id,
        )


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
