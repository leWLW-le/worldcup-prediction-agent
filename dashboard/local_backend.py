"""Single-instance loopback API for the free combined Streamlit deployment."""

import atexit
import threading
import time

import streamlit as st

LOCAL_URL = "http://127.0.0.1:8765"


@st.cache_resource(show_spinner=False)
def start_backend():
    import uvicorn

    # One process shares model/library memory across API and dashboard sessions.
    server = uvicorn.Server(
        uvicorn.Config(
            "main:app",
            host="127.0.0.1",
            port=8765,
            workers=1,
            log_level="info",
            timeout_graceful_shutdown=10,
        )
    )
    thread = threading.Thread(target=server.run, daemon=True, name="local-prediction-api")
    thread.start()
    atexit.register(setattr, server, "should_exit", True)
    deadline = time.monotonic() + 90
    while not server.started:
        if not thread.is_alive() or time.monotonic() >= deadline:
            server.should_exit = True
            raise RuntimeError("本机预测服务启动失败，请稍后重试。")
        time.sleep(0.1)
    return server


def backend_url():
    server = start_backend()
    if server.should_exit or not server.started:
        raise RuntimeError("本机预测服务已停止，请稍后重试。")
    return LOCAL_URL
