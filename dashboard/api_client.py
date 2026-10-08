import os

import httpx

from dashboard.config import load_dashboard_environment

load_dashboard_environment()
BASE_URL = os.getenv("BACKEND_URL", "http://localhost:8001").rstrip("/")


def api(method, path, token="", **kwargs):
    combined = os.getenv("COMBINED_SERVICE", "false").lower() == "true"
    base_url = BASE_URL
    if combined:
        from dashboard.local_backend import backend_url

        base_url = backend_url()
    headers = {"X-API-Key": token} if token else {}
    timeout = httpx.Timeout(15 if method == "GET" else 180, connect=5)
    try:
        response = httpx.request(
            method,
            base_url + "/api/v2" + path,
            headers=headers,
            timeout=timeout,
            trust_env=not combined,
            **kwargs,
        )
    except httpx.TimeoutException:
        raise RuntimeError("后端暂时没有响应，请稍后刷新页面。") from None
    except httpx.RequestError:
        raise RuntimeError("暂时无法连接预测服务，请稍后重试。") from None
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" in content_type or response.text.lstrip().lower().startswith(
        ("<!doctype html", "<html")
    ):
        raise RuntimeError("预测服务连接被网络验证拦截，请稍后重试。")
    if not response.is_success:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        if not isinstance(detail, str) or len(detail) > 300 or "<" in detail:
            detail = f"预测服务请求失败（HTTP {response.status_code}），请稍后重试。"
        raise RuntimeError(str(detail))
    try:
        return response.json()
    except ValueError:
        raise RuntimeError("预测服务返回了无效响应，请稍后重试。") from None
