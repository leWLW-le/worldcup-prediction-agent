"""Local dashboard configuration; deployment environment takes precedence."""

from pathlib import Path

from dotenv import load_dotenv


def load_dashboard_environment():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
