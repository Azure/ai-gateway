# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json

from azure.cli.core.azclierror import InvalidArgumentValueError


def parse_piped_resource_names(stream, list_command, resource_type):
    try:
        payload = json.load(stream)
    except json.JSONDecodeError as error:
        raise InvalidArgumentValueError(
            f"Piped input must be valid JSON from '{list_command} --output "
            f"json': {error.msg}."
        ) from error

    if not isinstance(payload, list):
        raise InvalidArgumentValueError(
            f"Piped input must be the JSON array produced by '{list_command} "
            "--output json'."
        )

    names = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise InvalidArgumentValueError(
                f"Piped item {index} must be a {resource_type} object."
            )
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise InvalidArgumentValueError(
                f"Piped {resource_type} at item {index} has no valid name."
            )
        names.append(name.strip())
    return names
