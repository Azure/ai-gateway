# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from urllib.parse import quote

from azure.cli.core.azclierror import (
    HTTPError,
    RequiredArgumentMissingError,
    ResourceNotFoundError,
)
from azure.cli.core.commands.client_factory import get_subscription_id

from azext_ai_gateway._gateway import (
    _gateway_path,
    _request,
    _response_json,
)

DEFAULT_WORKSPACE = "default"


def _provider_name(model):
    model_id = str(model.get("id") or "")
    marker = "/modelProviders/"
    marker_index = model_id.casefold().find(marker.casefold())
    if marker_index < 0:
        return ""
    provider_start = marker_index + len(marker)
    return model_id[provider_start:].split("/", 1)[0]


def format_model_list_table(models):
    return [
        {
            "Name": model.get("name") or "",
            "Type": (model.get("properties") or {}).get("providerKind") or "",
            "Provider name": _provider_name(model),
            "Endpoints": ", ".join(
                (model.get("properties") or {}).get("supportedEndpoints") or []
            ),
        }
        for model in models
    ]


def _models_path(
    subscription_id,
    resource_group_name,
    gateway_name,
    workspace_name,
    provider_name=None,
    model_name=None,
):
    path = (
        f"{_gateway_path(subscription_id, resource_group_name, gateway_name)}"
        f"/workspaces/{quote(workspace_name, safe='')}"
    )
    if provider_name is None:
        return f"{path}/models"
    path += f"/modelProviders/{quote(provider_name, safe='')}/models"
    if model_name is not None:
        path += f"/{quote(model_name, safe='')}"
    return path


def _raise_model_not_found(error, name):
    if error.response.status_code == 404:
        raise ResourceNotFoundError(f"Model '{name}' was not found.") from None
    raise error


def _list_all(cmd, url):
    models = []
    include_api_version = True
    while url:
        page = _response_json(
            _request(
                cmd,
                "GET",
                url,
                include_api_version=include_api_version,
            )
        )
        models.extend(page.get("value", []))
        url = page.get("nextLink")
        include_api_version = False
    return models


def _build_deployment(
    deployment_resource_id,
    deployment_model_name,
    deployment_model_version,
):
    if all(
        value is None
        for value in [
            deployment_resource_id,
            deployment_model_name,
            deployment_model_version,
        ]
    ):
        return None

    deployment = {}
    if deployment_resource_id is not None:
        deployment["resourceId"] = deployment_resource_id
    if deployment_model_name is not None:
        deployment["modelName"] = deployment_model_name
    if deployment_model_version is not None:
        deployment["modelVersion"] = deployment_model_version
    if not deployment.get("modelName"):
        raise RequiredArgumentMissingError(
            "Specify --deployment-model-name when configuring a deployment."
        )
    return deployment


def _build_properties(
    display_name=None,
    description=None,
    api_format=None,
    deployment_resource_id=None,
    deployment_model_name=None,
    deployment_model_version=None,
    supported_endpoints=None,
    policies=None,
):
    properties = {}
    if display_name is not None:
        properties["displayName"] = display_name
    if description is not None:
        properties["description"] = description
    if api_format is not None:
        properties["apiFormat"] = api_format
    deployment = _build_deployment(
        deployment_resource_id,
        deployment_model_name,
        deployment_model_version,
    )
    if deployment is not None:
        properties["deployment"] = deployment
    if supported_endpoints is not None:
        properties["supportedEndpoints"] = supported_endpoints
    if policies is not None:
        properties["policies"] = policies
    return properties


def list_models(
    cmd,
    gateway_name,
    resource_group_name,
    provider_name=None,
    workspace_name=DEFAULT_WORKSPACE,
    model_type=None,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _models_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        provider_name,
    )
    models = _list_all(cmd, path)
    if model_type is None:
        return models
    return [
        model
        for model in models
        if str(
            (model.get("properties") or {}).get("providerKind") or ""
        ).casefold()
        == model_type.casefold()
    ]


def show_model(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    provider_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _models_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        provider_name,
        name,
    )
    try:
        return _response_json(_request(cmd, "GET", path))
    except HTTPError as error:
        _raise_model_not_found(error, name)


def create_model(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    provider_name,
    workspace_name=DEFAULT_WORKSPACE,
    display_name=None,
    description=None,
    api_format=None,
    deployment_resource_id=None,
    deployment_model_name=None,
    deployment_model_version=None,
    supported_endpoints=None,
    policies=None,
):
    properties = _build_properties(
        display_name,
        description,
        api_format,
        deployment_resource_id,
        deployment_model_name,
        deployment_model_version,
        supported_endpoints,
        policies,
    )
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _models_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        provider_name,
        name,
    )
    return _response_json(_request(cmd, "PUT", path, {"properties": properties}))


def delete_model(
    cmd,
    name,
    gateway_name,
    resource_group_name,
    provider_name,
    workspace_name=DEFAULT_WORKSPACE,
):
    subscription_id = get_subscription_id(cmd.cli_ctx)
    path = _models_path(
        subscription_id,
        resource_group_name,
        gateway_name,
        workspace_name,
        provider_name,
        name,
    )
    _request(cmd, "DELETE", path)
