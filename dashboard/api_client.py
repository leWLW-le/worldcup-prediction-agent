import os

import httpx

BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8001").rstrip("/")


def api(method, path, token="", **kwargs):
    headers = {"X-API-Key": token} if token else {}
    timeout = httpx.Timeout(15 if method == "GET" else 180, connect=5)
    try:
        response = httpx.request(
            method, BASE_URL + "/api/v2" + path, headers=headers, timeout=timeout, **kwargs
        )
    except httpx.TimeoutException:
        raise RuntimeError("后端暂时没有响应，请稍后刷新页面。") from None
    if not response.is_success:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(str(detail))
    return response.json()
