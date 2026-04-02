"""Tests for EPI config API endpoints and protected-route security."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.security import rate_limiter


@pytest.fixture(autouse=True)
def reset_security_state() -> None:
    original_api_key = settings.API_KEY
    original_window = settings.RATE_LIMIT_WINDOW_SECONDS
    original_max = settings.RATE_LIMIT_MAX_REQUESTS

    settings.API_KEY = ""
    settings.RATE_LIMIT_WINDOW_SECONDS = 60
    settings.RATE_LIMIT_MAX_REQUESTS = 30
    rate_limiter.clear()
    try:
        yield
    finally:
        settings.API_KEY = original_api_key
        settings.RATE_LIMIT_WINDOW_SECONDS = original_window
        settings.RATE_LIMIT_MAX_REQUESTS = original_max
        rate_limiter.clear()


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    with TestClient(app) as c:
        yield c


class TestEpiConfigEndpoints:
    def test_get_epi_config(self, client: TestClient) -> None:
        resp = client.get("/api/config/epis")
        assert resp.status_code == 200

        data = resp.json()
        assert "epis" in data
        assert len(data["epis"]) == 6

        for item in data["epis"]:
            assert item["active"] is False
            assert "key" in item
            assert "label" in item

    def test_get_epi_config_keys(self, client: TestClient) -> None:
        resp = client.get("/api/config/epis")
        data = resp.json()

        keys = {item["key"] for item in data["epis"]}
        expected = {
            "luvas",
            "colete",
            "protecao_ocular",
            "capacete",
            "mascara",
            "calcado_seguranca",
        }
        assert keys == expected

    def test_post_epi_config(self, client: TestClient) -> None:
        resp = client.post(
            "/api/config/epis",
            json={"active_epis": ["capacete", "luvas"]},
        )
        assert resp.status_code == 200

        data = resp.json()
        active_items = [item for item in data["epis"] if item["active"]]
        active_keys = {item["key"] for item in active_items}
        assert active_keys == {"capacete", "luvas"}

        client.post("/api/config/epis", json={"active_epis": []})

    def test_post_epi_config_invalid_key(self, client: TestClient) -> None:
        resp = client.post(
            "/api/config/epis",
            json={"active_epis": ["invalid_epi"]},
        )
        assert resp.status_code == 400


class TestProtectedRouteSecurity:
    def test_requires_api_key_when_configured(self, client: TestClient) -> None:
        settings.API_KEY = "secret-key"

        resp = client.get("/api/config/epis")

        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid API key"

    def test_accepts_valid_api_key(self, client: TestClient) -> None:
        settings.API_KEY = "secret-key"

        resp = client.get("/api/config/epis", headers={"X-API-Key": "secret-key"})

        assert resp.status_code == 200

    def test_rate_limit_returns_429(self, client: TestClient) -> None:
        settings.API_KEY = "secret-key"
        settings.RATE_LIMIT_MAX_REQUESTS = 1
        settings.RATE_LIMIT_WINDOW_SECONDS = 60
        rate_limiter.clear()

        headers = {"X-API-Key": "secret-key"}

        first = client.post("/api/stream/stop", headers=headers)
        second = client.post("/api/stream/stop", headers=headers)

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.json()["detail"] == "Rate limit exceeded. Try again later."
