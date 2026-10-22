# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------------------------

import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from azure.cli.core.azclierror import AzCLIError, InvalidArgumentValueError

from azext_ai_gateway import _mcp, _model_alias


def _response(body=None, status=200, headers=None):
    return SimpleNamespace(
        json=lambda: body,
        status_code=status,
        ok=200 <= status < 400,
        headers=headers or {},
        text=json.dumps(body),
        content=json.dumps(body).encode(),
    )


@pytest.fixture(params=[_model_alias, _mcp])
def runtime(request, monkeypatch):
    module = request.param
    state = SimpleNamespace(
        attempts=0,
        failures=set(),
        network_error=False,
        failure_method=None if module is _model_alias else "initialize",
    )
    gateway = Mock(
        return_value={"properties": {"gatewayUrl": "https://gateway.test"}}
    )
    secrets = Mock(return_value={"primaryKey": "secret"})
    monkeypatch.setattr(module, "show_gateway", gateway)
    monkeypatch.setattr(module, "list_api_key_secrets", secrets)
    monkeypatch.setattr(module, "should_disable_connection_verify", lambda: False)
    if module is _model_alias:
        resource = Mock(
            return_value={
                "properties": {
                    "aliasName": "chat",
                    "backendModels": [
                        {"resourceId": "/modelProviders/provider/models/model"}
                    ],
                }
            }
        )
        monkeypatch.setattr(module, "show_model_alias", resource)
        monkeypatch.setattr(
            module,
            "show_model",
            Mock(
                return_value={
                    "properties": {
                        "supportedEndpoints": ["/openai/v1/chat/completions"]
                    }
                }
            ),
        )
        test = module.test_model_alias
    else:
        resource = Mock(return_value={"properties": {"failureMode": "failClosed"}})
        monkeypatch.setattr(module, "show_mcp", resource)
        test = module.test_mcp

    def post(_endpoint, **kwargs):
        method = kwargs["json"].get("method")
        if method in (None, "initialize"):
            state.attempts += 1
        if (
            state.attempts in state.failures
            and method == state.failure_method
        ):
            if state.network_error:
                raise requests.ConnectionError("Connection refused")
            return _response({"message": "Rate limit exceeded"}, status=429)
        if method == "initialize":
            return _response(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                    },
                },
                headers={"Mcp-Session-Id": f"session-{state.attempts}"},
            )
        if method == "notifications/initialized":
            return _response(status=202)
        if method == "tools/list":
            return _response(
                {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}}
            )
        return _response({"id": f"response-{state.attempts}"})

    post_mock = Mock(side_effect=post)
    monkeypatch.setattr(module.requests, "post", post_mock)
    return SimpleNamespace(
        module=module,
        state=state,
        gateway=gateway,
        secrets=secrets,
        resource=resource,
        post=post_mock,
        test=test,
        cmd=SimpleNamespace(cli_ctx=object()),
    )


def _run(runtime, n, name="target"):
    return runtime.test(
        runtime.cmd,
        name=name,
        gateway_name="gateway",
        resource_group_name="rg",
        api_key_name="key",
        n=n,
    )


@pytest.mark.parametrize("n", [1, 3])
def test_repetitions_send_exact_count_and_reuse_setup(runtime, n, caplog):
    result = _run(runtime, n)

    assert runtime.state.attempts == n
    assert isinstance(result, dict if n == 1 else list)
    if n > 1:
        assert len(result) == n
        assert "Test 3/3 for 'target': Succeeded." in caplog.text
    runtime.gateway.assert_called_once()
    runtime.secrets.assert_called_once()
    runtime.resource.assert_called_once()
    if runtime.module is _mcp:
        calls = runtime.post.call_args_list
        assert len(calls) == n * 3
        for index in range(n):
            initialize, initialized, tools = calls[index * 3:index * 3 + 3]
            assert "Mcp-Session-Id" not in initialize.kwargs["headers"]
            for session_call in (initialized, tools):
                assert session_call.kwargs["headers"]["Mcp-Session-Id"] == (
                    f"session-{index + 1}"
                )
    else:
        assert runtime.post.call_count == n


@pytest.mark.parametrize("failures", [{1}, {2}, {3}, {1, 2, 3}])
@pytest.mark.parametrize("network_error", [False, True])
def test_repetitions_continue_after_errors(
    runtime, failures, network_error, caplog
):
    runtime.state.failures = failures
    runtime.state.network_error = network_error

    with pytest.raises(
        AzCLIError,
        match=f"{3 - len(failures)} succeeded and {len(failures)} failed",
    ):
        _run(runtime, 3)

    assert runtime.state.attempts == 3
    for iteration in range(1, 4):
        status = "Failed" if iteration in failures else "Succeeded"
        assert f"Test {iteration}/3 for 'target': {status}." in caplog.text
    assert ("Connection refused" if network_error else "429") in caplog.text
    runtime.gateway.assert_called_once()
    runtime.secrets.assert_called_once()


@pytest.mark.parametrize("runtime", [_mcp], indirect=True)
@pytest.mark.parametrize(
    "failure_method", ["notifications/initialized", "tools/list"]
)
def test_repetitions_continue_after_late_mcp_failure(
    runtime, failure_method, caplog
):
    runtime.state.failures = {2}
    runtime.state.failure_method = failure_method

    with pytest.raises(AzCLIError, match="2 succeeded and 1 failed"):
        _run(runtime, 3)

    assert runtime.state.attempts == 3
    assert failure_method in caplog.text
    assert "429" in caplog.text
    assert "Test 3/3 for 'target': Succeeded." in caplog.text


@pytest.mark.parametrize("n", [0, -1, 1.5, "2", None, True])
def test_invalid_count_rejected_before_requests(runtime, n):
    with pytest.raises(InvalidArgumentValueError, match="positive integer"):
        _run(runtime, n)

    runtime.resource.assert_not_called()
    runtime.gateway.assert_not_called()
    runtime.secrets.assert_not_called()
    runtime.post.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_piped_repetitions_test_every_resource(runtime, monkeypatch, fail):
    stream = StringIO(json.dumps([{"name": "one"}, {"name": "two"}]))
    monkeypatch.setattr(runtime.module.sys, "stdin", stream)
    if fail:
        runtime.state.failures = {2}
        with pytest.raises(AzCLIError, match="batch test completed"):
            _run(runtime, 3, name=None)
    else:
        results = _run(runtime, 3, name=None)
        assert len(results) == 6

    assert runtime.state.attempts == 6
    assert [call.args[1] for call in runtime.resource.call_args_list] == [
        "one",
        "two",
    ]
    assert runtime.gateway.call_count == 2
    assert runtime.secrets.call_count == 2
