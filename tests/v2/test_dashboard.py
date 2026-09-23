from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def test_dashboard_empty_state_and_backend_failure():
    with patch("dashboard.api_client.api", return_value={"snapshots": []}):
        app = AppTest.from_file("dashboard/app.py").run()
        assert not app.exception
        assert any("尚无赛事快照" in item.value for item in app.info)
    with patch("dashboard.api_client.api", side_effect=RuntimeError("offline")):
        app = AppTest.from_file("dashboard/app.py").run()
        assert not app.exception
        assert "offline" in app.error[0].value
