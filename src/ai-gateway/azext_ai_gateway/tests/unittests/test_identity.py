# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from azure.cli.core.azclierror import RequiredArgumentMissingError

from azext_ai_gateway import _identity


class FakeResponse:

    def __init__(self, body=None):
        self._body = body
        self.content = b"" if body is None else json.dumps(body).encode()

    def json(self):
        return self._body


@pytest.fixture
def cmd():
    return SimpleNamespace(cli_ctx=object())


@patch("azext_ai_gateway._identity.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._identity._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_assign_system_identity_preserves_user_assigned_identities(
    send_request,
    wait_for_gateway,
    _,
    cmd,
):
    identity_id = "/identities/existing"
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
        "identity": {
            "type": "SystemAssigned, UserAssigned",
            "userAssignedIdentities": {identity_id: {}},
        }
    }

    result = _identity.assign_identity(
        cmd,
        "gateway",
        "rg",
        system_assigned=True,
    )

    body = json.loads(send_request.call_args_list[1].kwargs["body"])
    assert body == {"identity": {"type": "SystemAssigned, UserAssigned"}}
    assert result["type"] == "SystemAssigned, UserAssigned"


@patch("azext_ai_gateway._identity.get_subscription_id", return_value="sub")
@patch("azext_ai_gateway._identity._wait_for_gateway")
@patch("azext_ai_gateway._gateway.send_raw_request")
def test_remove_all_user_assigned_identities_uses_null_entries(
    send_request,
    wait_for_gateway,
    _,
    cmd,
):
    send_request.side_effect = [
        FakeResponse(
            {
                "identity": {
                    "type": "SystemAssigned, UserAssigned",
                    "userAssignedIdentities": {
                        "/identities/one": {},
                        "/identities/two": {},
                    },
                }
            }
        ),
        FakeResponse({"properties": {"provisioningState": "Updating"}}),
    ]
    wait_for_gateway.return_value = {"identity": {"type": "SystemAssigned"}}

    _identity.remove_identity(
        cmd,
        "gateway",
        "rg",
        user_assigned=[],
    )

    body = json.loads(send_request.call_args_list[1].kwargs["body"])
    assert body == {
        "identity": {
            "type": "SystemAssigned",
            "userAssignedIdentities": {
                "/identities/one": None,
                "/identities/two": None,
            },
        }
    }


def test_identity_change_requires_a_selection(cmd):
    with pytest.raises(RequiredArgumentMissingError):
        _identity.assign_identity(cmd, "gateway", "rg")
    with pytest.raises(RequiredArgumentMissingError):
        _identity.remove_identity(cmd, "gateway", "rg")

