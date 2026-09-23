from fastapi.testclient import TestClient

from app.core.config import get_settings
from main import app


def test_api_auth_bounds_and_results(service, snapshot, monkeypatch):
    app.state.services = service
    monkeypatch.setattr(get_settings(), "ADMIN_API_KEY", "test-key")
    client = TestClient(app)
    body = {"snapshot_id": snapshot.snapshot_id, "simulation_count": 100}
    assert client.post("/api/v2/predictions", json=body).status_code == 401
    headers = {"X-API-Key": "test-key"}
    assert (
        client.post(
            "/api/v2/predictions", json={**body, "simulation_count": 10**9}, headers=headers
        ).status_code
        == 422
    )
    assert client.get("/api/v2/tournament-state").status_code == 200
    assert client.post("/api/v1/agent/run-prediction", json={}).status_code == 410
    response = client.post("/api/v2/predictions", json=body, headers=headers)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    # The integration checks real async execution, not mocked response shapes.
    import time

    for _ in range(100):
        job = client.get("/api/v2/jobs/" + job_id).json()
        if job["status"] != "running":
            break
        time.sleep(0.01)
    assert job["status"] == "completed"
    assert client.get("/api/v2/results/" + job["run_id"]).status_code == 200


def test_env_precedes_dotenv(tmp_path, monkeypatch):
    from app.core.config import Settings

    (tmp_path / ".env").write_text("LLM_MODEL=from_file\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_MODEL", "from_env")
    assert Settings().LLM_MODEL == "from_env"


def test_missing_llm_does_not_disable_prediction(service, monkeypatch):
    monkeypatch.setattr(get_settings(), "LLM_API_KEY", "")
    app.state.services = service
    client = TestClient(app)
    assert client.get("/api/v2/tournament-state").status_code == 200


def test_request_body_budget(service, monkeypatch):
    app.state.services = service
    monkeypatch.setattr(get_settings(), "MAX_REQUEST_BYTES", 1024)
    response = TestClient(app).post("/api/v2/snapshots", content=b"x"*1025)
    assert response.status_code == 413
