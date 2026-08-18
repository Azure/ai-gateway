# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from importlib.metadata import version

from azure.cli.core.azclierror import AzCLIError

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

# pylint: disable=unused-argument,unused-import


def import_from_apim(
    name,
    resource_group_name,
    source_apim_id,
    include=None,
    conflict_policy="fail",
    mapping_file=None,
    dry_run=False,
    no_wait=False,
):
    raise AzCLIError(
        "Import from Azure API Management is not implemented yet.",
        recommendation=(
            "Use 'az ai-gateway import --help' to review the planned command contract."
        ),
    )


def show_version():
    return {
        "extensionName": "ai-gateway",
        "extensionVersion": version("ai-gateway"),
        "status": "preview",
    }
