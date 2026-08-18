# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from pathlib import Path

from azure.cli.core.azclierror import FileOperationError, InvalidArgumentValueError
from azure.cli.core.util import shell_safe_json_parse


def validate_policies(value):
    parsed = _parse_json_value(value, "Policies")
    if not isinstance(parsed, list) or any(
        not isinstance(policy, dict) or not policy.get("type")
        for policy in parsed
    ):
        raise InvalidArgumentValueError(
            "Policies must be a JSON array of objects that each contain 'type'."
        )
    return parsed


def validate_policy(value):
    parsed = _parse_json_value(value, "Policy")
    if not isinstance(parsed, dict) or not parsed.get("type"):
        raise InvalidArgumentValueError(
            "Policy must be a JSON object that contains 'type'."
        )
    return parsed


def validate_endpoints(value):
    parsed = _parse_json_value(value, "Endpoints")
    if not isinstance(parsed, list) or not parsed:
        raise InvalidArgumentValueError(
            "Endpoints must be a non-empty JSON array."
        )
    if any(
        not isinstance(endpoint, dict)
        or not endpoint.get("namespace")
        or endpoint.get("kind") not in {"mcp", "openApi", "http"}
        for endpoint in parsed
    ):
        raise InvalidArgumentValueError(
            "Each endpoint must contain 'namespace' and a supported 'kind'."
        )
    return parsed


def _parse_json_value(value, label):
    try:
        if value.startswith("@"):
            parsed = json.loads(
                Path(value[1:]).expanduser().read_text(encoding="utf-8")
            )
        else:
            parsed = shell_safe_json_parse(value)
    except OSError as error:
        raise FileOperationError(str(error)) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise InvalidArgumentValueError(
            f"{label} must be JSON or a path prefixed with '@'."
        ) from error
    return parsed
