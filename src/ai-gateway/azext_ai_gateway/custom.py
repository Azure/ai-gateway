# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from importlib.metadata import version

from azext_ai_gateway._gateway import (
    create_gateway,
    delete_gateway,
    list_gateways,
    show_gateway,
    update_gateway,
)
from azext_ai_gateway._model import (
    create_model,
    delete_model,
    list_models,
    show_model,
    update_model,
)
from azext_ai_gateway._mcp import (
    authorize_mcp,
    create_mcp,
    delete_mcp,
    list_mcp,
    show_mcp,
    update_mcp,
)
from azext_ai_gateway._api_key import (
    create_api_key,
    delete_api_key,
    list_api_key_secrets,
    list_api_keys,
    regenerate_api_key,
    show_api_key,
)
from azext_ai_gateway._identity import (
    assign_identity,
    remove_identity,
    show_identity,
)
from azext_ai_gateway._policy import (
    create_policy,
    delete_policy,
    list_policies,
    show_policy,
    update_policy,
)
from azext_ai_gateway._import import import_from_apim
from azext_ai_gateway._policy_translation import (
    list_policy_translation_support,
    show_policy_translation_support,
)

# pylint: disable=unused-argument,unused-import


def show_version():
    return {
        "extensionName": "ai-gateway",
        "extensionVersion": version("ai-gateway"),
        "status": "preview",
    }
