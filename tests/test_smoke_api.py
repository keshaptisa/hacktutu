from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_create_escape_smoke_demo_mode(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    monkeypatch.setenv("MCP_ENABLED", "false")
    monkeypatch.setenv("LLM_ENABLED", "false")

    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/api/escape",
            json={
                "budget_rub": 35000,
                "duration_hours": 72,
                "moods": ["spontaneity", "impressions"],
                "wishes": ["без долгих переездов", "хочу исторический город"],
                "origin": "Москва",
            },
        )

    get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["scenarios"]) == 3
    assert payload["degraded"] is True
    assert payload["data_origin"] == "demo"
