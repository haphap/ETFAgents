import unittest
from unittest.mock import MagicMock, patch

from cli.main import (
    _format_runtime_failure,
    _is_local_backend_url,
    _preflight_local_backend,
)


class CliRuntimeHandlingTests(unittest.TestCase):
    def test_is_local_backend_url_detects_loopback_hosts(self):
        self.assertTrue(_is_local_backend_url("http://127.0.0.1:8020/v1"))
        self.assertTrue(_is_local_backend_url("http://localhost:4000/v1"))
        self.assertFalse(_is_local_backend_url("https://api.openai.com/v1"))

    def test_preflight_local_backend_raises_friendly_runtime_error(self):
        with patch("requests.get", side_effect=ConnectionRefusedError(111, "Connection refused")):
            with self.assertRaises(RuntimeError) as ctx:
                _preflight_local_backend("vllm", "http://127.0.0.1:8020/v1")

        self.assertIn("Cannot reach vLLM backend at http://127.0.0.1:8020/v1", str(ctx.exception))

    def test_preflight_local_backend_accepts_healthy_server(self):
        response = MagicMock()
        response.raise_for_status.return_value = None

        with patch("requests.get", return_value=response) as mock_get:
            _preflight_local_backend("vllm", "http://127.0.0.1:8020/v1")

        mock_get.assert_called_once_with("http://127.0.0.1:8020/v1/models", timeout=3)

    def test_format_runtime_failure_summarizes_connection_refusal(self):
        try:
            try:
                raise ConnectionRefusedError(111, "Connection refused")
            except ConnectionRefusedError as inner:
                raise RuntimeError("wrapper") from inner
        except RuntimeError as exc:
            message = _format_runtime_failure(
                exc,
                {"llm_provider": "vllm", "backend_url": "http://127.0.0.1:8020/v1"},
            )

        self.assertEqual(
            message,
            "Cannot reach vLLM backend at http://127.0.0.1:8020/v1. Start the server first, or choose a different provider.",
        )


if __name__ == "__main__":
    unittest.main()
