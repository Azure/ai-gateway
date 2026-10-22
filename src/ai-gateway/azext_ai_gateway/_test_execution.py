# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from azure.cli.core.azclierror import AzCLIError, InvalidArgumentValueError
from knack.log import get_logger

logger = get_logger(__name__)


def validate_test_count(n):
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise InvalidArgumentValueError("--n must be a positive integer.")


def run_test_repetitions(n, resource_name, test):
    if n == 1:
        return test()

    results = []
    failures = 0
    for iteration in range(1, n + 1):
        try:
            results.append(test())
        except AzCLIError as error:
            failures += 1
            logger.warning(
                "Test %d/%d for '%s': Failed. %s",
                iteration,
                n,
                resource_name,
                error,
            )
        else:
            logger.warning(
                "Test %d/%d for '%s': Succeeded.",
                iteration,
                n,
                resource_name,
            )
    if failures:
        raise AzCLIError(
            f"Tests for '{resource_name}' completed with "
            f"{len(results)} succeeded and {failures} failed."
        )
    return results
