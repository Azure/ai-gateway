# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import ipaddress
import json
import re
from pathlib import Path

from azure.cli.core.azclierror import FileOperationError, InvalidArgumentValueError
from azure.cli.core.util import shell_safe_json_parse


_COUNTER_KEYS = {"IPAddress", "Identity"}
_SEVERITIES = {"Low", "Medium", "High", "None"}
_COST_PERIODS = {"hour", "day", "week", "month", "year"}
_TOKEN_PERIODS = {"minute", "hour", "day"}
_COST_AMOUNT_MIN = 0.000000001
_COST_AMOUNT_MAX = 10_000_000
_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_RESTRICTED_RESPONSE_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "transfer-encoding",
}


def validate_policies(value):
    parsed = _parse_json_value(value, "Policies")
    if not isinstance(parsed, list) or any(
        not isinstance(policy, dict)
        or not isinstance(policy.get("type"), str)
        or not policy["type"].strip()
        for policy in parsed
    ):
        raise InvalidArgumentValueError(
            "Policies must be a JSON array of objects that each contain a "
            "non-empty string 'type'."
        )
    for policy in parsed:
        _validate_known_policy(policy)
    return parsed


def validate_policy(value):
    parsed = _parse_json_value(value, "Policy")
    if (
        not isinstance(parsed, dict)
        or not isinstance(parsed.get("type"), str)
        or not parsed["type"].strip()
    ):
        raise InvalidArgumentValueError(
            "Policy must be a JSON object that contains a non-empty string "
            "'type'."
        )
    _validate_known_policy(parsed)
    return parsed


def _validate_known_policy(policy):
    policy_type = policy["type"]
    validators = {
        "tokenLimit": _validate_token_limit,
        "costLimit": _validate_cost_limit,
        "requestRateLimit": _validate_request_rate_limit,
        "contentSafety": _validate_content_safety,
        "ipFilter": _validate_ip_filter,
    }
    validator = validators.get(policy_type)
    if validator:
        validator(policy)


def _validate_token_limit(policy):
    _require_positive_integer(policy, "count", "tokenLimit")
    _require_enum(policy, "period", _TOKEN_PERIODS, "tokenLimit")
    _require_enum(policy, "counterKey", _COUNTER_KEYS, "tokenLimit")


def _validate_cost_limit(policy):
    amount = policy.get("amount")
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not _COST_AMOUNT_MIN <= amount <= _COST_AMOUNT_MAX
    ):
        raise InvalidArgumentValueError(
            "costLimit.amount must be a number from 0.000000001 to 10000000."
        )
    _require_enum(policy, "period", _COST_PERIODS, "costLimit")
    _require_enum(policy, "counterKey", _COUNTER_KEYS, "costLimit")
    _require_optional_string(policy, "displayName", "costLimit")
    _require_optional_string(policy, "remainingCostHeaderName", "costLimit")
    header_name = policy.get("remainingCostHeaderName")
    if header_name and (
        not _HEADER_NAME_PATTERN.fullmatch(header_name)
        or header_name.casefold() in _RESTRICTED_RESPONSE_HEADERS
    ):
        raise InvalidArgumentValueError(
            "costLimit.remainingCostHeaderName must be a valid response header "
            "other than Connection, Content-Length, Keep-Alive, or "
            "Transfer-Encoding."
        )


def _validate_request_rate_limit(policy):
    _require_positive_integer(
        policy,
        "callsPerPeriod",
        "requestRateLimit",
    )
    _require_positive_integer(
        policy,
        "periodSeconds",
        "requestRateLimit",
    )
    _require_enum(
        policy,
        "counterKey",
        _COUNTER_KEYS,
        "requestRateLimit",
    )


def _validate_content_safety(policy):
    for field in [
        "hateSeverity",
        "violenceSeverity",
        "sexualSeverity",
        "selfHarmSeverity",
    ]:
        _require_enum(policy, field, _SEVERITIES, "contentSafety")


def _validate_ip_filter(policy):
    _require_enum(policy, "action", {"Allow", "Deny"}, "ipFilter")
    cidr_ranges = policy.get("cidrRanges")
    if not isinstance(cidr_ranges, list) or not cidr_ranges:
        raise InvalidArgumentValueError(
            "ipFilter.cidrRanges must be a non-empty array of IPv4 CIDR ranges."
        )
    for cidr_range in cidr_ranges:
        if not isinstance(cidr_range, str) or "/" not in cidr_range:
            raise InvalidArgumentValueError(
                "ipFilter.cidrRanges must contain valid IPv4 CIDR ranges."
            )
        try:
            network = ipaddress.ip_network(cidr_range, strict=False)
        except (TypeError, ValueError) as error:
            raise InvalidArgumentValueError(
                "ipFilter.cidrRanges must contain valid IPv4 CIDR ranges."
            ) from error
        if network.version != 4:
            raise InvalidArgumentValueError(
                "ipFilter.cidrRanges must contain valid IPv4 CIDR ranges."
            )


def _require_positive_integer(policy, field, policy_type):
    value = policy.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise InvalidArgumentValueError(
            f"{policy_type}.{field} must be a positive integer."
        )


def _require_enum(policy, field, values, policy_type):
    if policy.get(field) not in values:
        choices = ", ".join(sorted(values))
        raise InvalidArgumentValueError(
            f"{policy_type}.{field} must be one of: {choices}."
        )


def _require_optional_string(policy, field, policy_type):
    if field in policy and not isinstance(policy[field], str):
        raise InvalidArgumentValueError(
            f"{policy_type}.{field} must be a string."
        )


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


def validate_headers(value):
    parsed = _parse_json_value(value, "Headers")
    if not isinstance(parsed, dict) or not parsed:
        raise InvalidArgumentValueError(
            "Headers must be a JSON object with non-empty string names and values."
        )
    normalized_names = []
    for name, header_value in parsed.items():
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(header_value, str)
            or not header_value.strip()
        ):
            raise InvalidArgumentValueError(
                "Headers must be a JSON object with non-empty string names and "
                "values."
            )
        normalized_names.append(name.strip().casefold())
    if len(set(normalized_names)) != len(normalized_names):
        raise InvalidArgumentValueError(
            "Header names must be unique, ignoring case."
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
