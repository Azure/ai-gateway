import contextlib
import importlib.util
import io
import ipaddress
import json
import urllib.error
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "probe", Path(__file__).parents[1] / "scripts" / "private-path-probe.py"
)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class PrivatePathProbeTests(unittest.TestCase):
    def test_rejects_public_or_wrong_private_dns(self):
        for addresses in (["10.247.1.4", "20.10.0.1"], ["10.20.1.4"], []):
            records = [(2, 1, 6, "", (address, 443)) for address in addresses]
            with self.subTest(addresses=addresses), patch.object(probe.socket, "getaddrinfo", return_value=records):
                with self.assertRaises(RuntimeError):
                    probe.private_dns("gateway.example", ipaddress.ip_network("10.247.1.0/24"))

    def run_probe(self, replies):
        configuration = {
            "gateway_id": "/subscriptions/test/resourceGroups/test/providers/Microsoft.ApiManagement/service/test",
            "gateway_endpoint": "https://gateway.example",
            "model_endpoint": "https://model.example",
            "private_endpoint_subnet": "10.247.1.0/24",
            "model_names": ["mini", "full"],
            "model_apis": {
                model: {
                    "api_format": "OpenAIChatCompletions",
                    "endpoints": ["/openai/v1/chat/completions", "/openai/v1/responses"],
                }
                for model in ("mini", "full")
            },
        }
        responses = [
            (200, {"access_token": "test-token-must-not-appear"}),
            (200, {"primaryKey": "test-key-must-not-appear"}),
        ] + [(200, {"choices": [{"message": {"content": reply}}]}) for reply in replies] + [
            urllib.error.HTTPError("https://gateway.example", 401, "Unauthorized", {}, None),
            urllib.error.HTTPError("https://gateway.example", 401, "Unauthorized", {}, None),
        ]
        output = io.StringIO()
        with patch.object(probe.sys, "argv", ["probe", "--configuration", json.dumps(configuration)]), \
                patch.object(probe.socket, "getaddrinfo", return_value=[(2, 1, 6, "", ("10.247.1.4", 443))]), \
                patch.object(probe, "request_json", side_effect=responses), contextlib.redirect_stdout(output):
            probe.main()
        return output.getvalue()

    def test_checks_all_aliases_without_emitting_credentials(self):
        output = self.run_probe(["OK", "OK"])
        result = json.loads(output)
        self.assertTrue(result["passed"])
        self.assertEqual(["mini", "full"], [entry["model"] for entry in result["inference"]])
        self.assertEqual([401, 401], [entry["status"] for entry in result["authentication"]])
        for entry in result["inference"]:
            self.assertRegex(entry["trace_id"], r"^[a-f0-9]{32}$")
        self.assertNotIn("test-token-must-not-appear", output)
        self.assertNotIn("test-key-must-not-appear", output)

    def test_rejects_success_status_with_wrong_model_reply(self):
        with self.assertRaisesRegex(RuntimeError, "Inference failed for full"):
            self.run_probe(["OK", "unexpected"])

    def test_negative_auth_requires_a_real_rejection(self):
        for code, message, accepted in (
            (401, "Unauthorized", True),
            (403, "Invalid API key", True),
            (403, "Blocked by firewall", False),
            (500, "Internal error", False),
            (429, "Rate limited", False),
        ):
            error = urllib.error.HTTPError(
                "https://gateway.example", code, message, {},
                io.BytesIO(json.dumps({"message": message}).encode()),
            )
            with self.subTest(code=code, message=message), \
                    patch.object(probe, "request_json", side_effect=error):
                if accepted:
                    self.assertEqual(code, probe.check_key_rejection(None, "https://gateway.example", {}, {}))
                else:
                    with self.assertRaisesRegex(RuntimeError, "not proven"):
                        probe.check_key_rejection(None, "https://gateway.example", {}, {})
        with patch.object(probe, "request_json", return_value=(200, {})):
            with self.assertRaisesRegex(RuntimeError, "accepted"):
                probe.check_key_rejection(None, "https://gateway.example", {}, {})

    def test_rejects_unsupported_apis_before_dns_or_credentials(self):
        for metadata in (
            None,
            {},
            {"mini": {"api_format": "OpenAIChatCompletions", "endpoints": ["/openai/v1/responses"]}},
            {"mini": {"api_format": "Other", "endpoints": ["/openai/v1/chat/completions"]}},
            {"mini": {"api_format": "OpenAIChatCompletions", "endpoints": []}},
        ):
            configuration = {"model_names": ["mini"], "model_apis": metadata}
            with self.subTest(metadata=metadata), \
                    patch.object(probe.sys, "argv", ["probe", "--configuration", json.dumps(configuration)]), \
                    patch.object(probe.socket, "getaddrinfo") as dns, \
                    patch.object(probe, "request_json") as request:
                with self.assertRaisesRegex(RuntimeError, "metadata|Unsupported probe API"):
                    probe.main()
                dns.assert_not_called()
                request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
