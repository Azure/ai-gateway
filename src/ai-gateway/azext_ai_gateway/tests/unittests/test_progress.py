# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from azext_ai_gateway import _progress


class FakeConfig:

    def __init__(self, disable_progress_bar=False):
        self.disable_progress_bar = disable_progress_bar

    def getboolean(self, section, option, default):
        assert (section, option, default) == (
            "core",
            "disable_progress_bar",
            False,
        )
        return self.disable_progress_bar


def _cmd(disable_progress_bar=False, only_show_errors=False):
    return SimpleNamespace(
        cli_ctx=SimpleNamespace(
            config=FakeConfig(disable_progress_bar),
            only_show_errors=only_show_errors,
            get_progress_controller=Mock(),
        )
    )


@patch("azext_ai_gateway._progress.logger.warning")
def test_report_lro_accepted_uses_warning_channel(warning):
    cmd = _cmd()

    _progress.report_lro_accepted(cmd, "Request accepted.")

    warning.assert_called_once_with("Request accepted.")


@patch("azext_ai_gateway._progress.logger.warning")
def test_report_lro_accepted_honors_only_show_errors(warning):
    _progress.report_lro_accepted(
        _cmd(only_show_errors=True),
        "Request accepted.",
    )

    warning.assert_not_called()


@patch("azure.cli.core.commands.progress.IndeterminateProgressBar")
def test_progress_animates_and_ends_on_success(progress_bar):
    indicator = progress_bar.return_value
    with (
        patch(
            "azext_ai_gateway._progress.time.monotonic",
            side_effect=[0, 0, 0.5, 1.0],
        ),
        patch("azext_ai_gateway._progress.time.sleep") as sleep,
    ):
        with _progress.long_running_progress(
            _cmd(),
            "Waiting for resource",
        ) as progress:
            progress.update("Waiting for resource (state: Creating)")
            progress.wait(1)

    indicator.begin.assert_called_once_with()
    assert indicator.update_progress_with_msg.call_args_list == [
        call("Waiting for resource"),
        call("Waiting for resource (state: Creating)"),
        call("Waiting for resource (state: Creating)"),
        call("Waiting for resource (state: Creating)"),
    ]
    assert sleep.call_args_list == [call(0.5), call(0.5)]
    indicator.end.assert_called_once_with()
    indicator.stop.assert_not_called()


@patch("azure.cli.core.commands.progress.IndeterminateProgressBar")
def test_progress_stops_on_failure(progress_bar):
    indicator = progress_bar.return_value

    with pytest.raises(RuntimeError, match="failed"):
        with _progress.long_running_progress(_cmd(), "Waiting"):
            raise RuntimeError("failed")

    indicator.stop.assert_called_once_with()
    indicator.end.assert_not_called()


@pytest.mark.parametrize(
    "cmd",
    [
        _cmd(disable_progress_bar=True),
        _cmd(only_show_errors=True),
        SimpleNamespace(cli_ctx=object()),
    ],
)
@patch("azure.cli.core.commands.progress.IndeterminateProgressBar")
def test_progress_is_noop_when_suppressed(progress_bar, cmd):
    with patch("azext_ai_gateway._progress.time.sleep") as sleep:
        with _progress.long_running_progress(cmd, "Waiting") as progress:
            progress.wait(5)

    progress_bar.assert_not_called()
    sleep.assert_called_once_with(5)
