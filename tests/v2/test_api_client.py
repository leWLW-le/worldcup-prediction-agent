from unittest.mock import patch

import httpx
import pytest

from dashboard.api_client import api


def test_combined_service_calls_loopback_only(monkeypatch):
    monkeypatch.setenv("COMBINED_SERVICE", "true")
    with (
        patch("dashboard.local_backend.backend_url", return_value="http://127.0.0.1:8765"),
        patch(
            "dashboard.api_client.httpx.request",
            return_value=httpx.Response(200, json={"ok": True}),
        ) as request,
    ):
        assert api("POST", "/coordinator", "test-server-key", json={}) == {"ok": True}
    assert request.call_args.args[1] == "http://127.0.0.1:8765/api/v2/coordinator"
    assert request.call_args.kwargs["trust_env"] is False
    assert request.call_args.kwargs["headers"]["X-API-Key"] == "test-server-key"


@pytest.mark.parametrize("status", [200, 403, 503])
def test_html_challenge_is_not_exposed(status):
    response = httpx.Response(
        status,
        text="<!DOCTYPE html><script>challenge-secret</script>",
        headers={"content-type": "text/html"},
    )
    with patch("dashboard.api_client.httpx.request", return_value=response):
        with pytest.raises(RuntimeError, match="网络验证") as error:
            api("POST", "/coordinator", "server-key", json={})
    assert "script" not in str(error.value)
    assert "challenge-secret" not in str(error.value)


def test_valid_error_remains_readable():
    with patch(
        "dashboard.api_client.httpx.request",
        return_value=httpx.Response(429, json={"detail": "Coordinator is busy"}),
    ):
        with pytest.raises(RuntimeError, match="Coordinator is busy"):
            api("POST", "/coordinator")
