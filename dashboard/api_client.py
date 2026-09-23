import os

import httpx

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8001").rstrip("/")


def api(method, path, token="", **kwargs):
    headers = {"X-API-Key": token} if token else {}
    response = httpx.request(
        method, BASE_URL + "/api/v2" + path, headers=headers, timeout=180, **kwargs
    )
    if not response.is_success:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(str(detail))
    return response.json()
