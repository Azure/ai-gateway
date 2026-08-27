# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from unittest.mock import patch

from azext_ai_gateway.custom import show_version


def test_show_version_returns_structured_extension_metadata():
    with patch("azext_ai_gateway.custom.version", return_value="1.0.0b1"):
        assert show_version() == {
            "extensionName": "ai-gateway",
            "extensionVersion": "1.0.0b1",
            "status": "preview",
        }
