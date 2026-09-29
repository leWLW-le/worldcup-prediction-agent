from unittest.mock import patch

import httpx
import pytest

from dashboard.api_client import api


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
