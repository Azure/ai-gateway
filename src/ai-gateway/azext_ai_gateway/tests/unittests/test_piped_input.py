# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from io import StringIO

import pytest
from azure.cli.core.azclierror import InvalidArgumentValueError

from azext_ai_gateway._piped_input import parse_piped_resource_names


def test_parse_piped_resource_names_accepts_empty_list():
    assert parse_piped_resource_names(
        StringIO("[]"),
        "az ai-gateway mcp list",
        "MCP tool server",
    ) == []


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("not-json", "must be valid JSON"),
        ('{"name": "one"}', "must be the JSON array"),
        ('["one"]', "item 0 must be"),
        ('[{"name": ""}]', "has no valid name"),
    ],
)
def test_parse_piped_resource_names_rejects_invalid_input(payload, message):
    with pytest.raises(InvalidArgumentValueError, match=message):
        parse_piped_resource_names(
            StringIO(payload),
            "az ai-gateway model-alias list",
            "model alias",
        )
