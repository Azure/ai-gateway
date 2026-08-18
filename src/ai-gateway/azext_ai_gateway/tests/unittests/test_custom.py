# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from unittest.mock import patch

import pytest
from azure.cli.core.azclierror import AzCLIError

from azext_ai_gateway.custom import import_from_apim, show_version


def test_import_from_apim_fails_explicitly_until_service_is_wired():
    with pytest.raises(AzCLIError, match="not implemented yet"):
        import_from_apim(
            name="destination",
            resource_group_name="destination-rg",
            source_apim_id=(
                "/subscriptions/00000000-0000-0000-0000-000000000000/"
                "resourceGroups/source-rg/providers/"
                "Microsoft.ApiManagement/service/source"
            ),
        )


def test_show_version_returns_structured_extension_metadata():
    with patch("azext_ai_gateway.custom.version", return_value="1.0.0b1"):
        assert show_version() == {
            "extensionName": "ai-gateway",
            "extensionVersion": "1.0.0b1",
            "status": "preview",
        }
