# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import time
from contextlib import contextmanager

from knack.log import get_logger

logger = get_logger(__name__)

PROGRESS_REFRESH_SECONDS = 0.5


def report_lro_accepted(cmd, message):
    if getattr(cmd.cli_ctx, "only_show_errors", False):
        return
    logger.warning(message)


class LongRunningProgress:

    def __init__(self, cmd, message):
        self._message = message
        self._indicator = None
        cli_ctx = cmd.cli_ctx
        config = getattr(cli_ctx, "config", None)
        disabled = getattr(cli_ctx, "only_show_errors", False)
        if config is not None:
            disabled = disabled or config.getboolean(
                "core",
                "disable_progress_bar",
                False,
            )
        if not disabled and hasattr(cli_ctx, "get_progress_controller"):
            from azure.cli.core.commands.progress import (
                IndeterminateProgressBar,
            )

            self._indicator = IndeterminateProgressBar(
                cli_ctx,
                message=message,
            )

    def begin(self):
        if self._indicator:
            self._indicator.begin()
            self._indicator.update_progress_with_msg(self._message)

    def update(self, message=None):
        if message:
            self._message = message
        if self._indicator:
            self._indicator.update_progress_with_msg(self._message)

    def wait(self, seconds):
        if not self._indicator:
            time.sleep(seconds)
            return
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.update()
            time.sleep(min(PROGRESS_REFRESH_SECONDS, remaining))

    def end(self):
        if self._indicator:
            self._indicator.end()

    def stop(self):
        if self._indicator:
            self._indicator.stop()


@contextmanager
def long_running_progress(cmd, message):
    progress = LongRunningProgress(cmd, message)
    progress.begin()
    try:
        yield progress
    except BaseException:
        progress.stop()
        raise
    else:
        progress.end()
