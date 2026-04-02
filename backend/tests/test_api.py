"""Tests for EPI config API endpoints (CONF-01).

Covers: GET/POST /api/config/epis endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    """FastAPI TestClient using real app with real stream_processor (no camera/model needed for config)."""
    from app.main import app

    with TestClient(app) as c:
        yield c


class TestEpiConfigEndpoints:
    """CONF-01: GET/POST /api/config/epis endpoints."""

    def test_get_epi_config(self, client: TestClient) -> None:
        """GET /api/config/epis returns 6 items, all inactive by default."""
        resp = client.get("/api/config/epis")
        assert resp.status_code == 200

        data = resp.json()
        assert "epis" in data
        assert len(data["epis"]) == 6

        # All should be inactive by default
        for item in data["epis"]:
            assert item["active"] is False
            assert "key" in item
            assert "label" in item

    def test_get_epi_config_keys(self, client: TestClient) -> None:
        """GET /api/config/epis returns all 6 expected EPI keys."""
        resp = client.get("/api/config/epis")
        data = resp.json()

        keys = {item["key"] for item in data["epis"]}
        expected = {"luvas", "colete", "protecao_ocular", "capacete", "mascara", "calcado_seguranca"}
        assert keys == expected

    def test_post_epi_config(self, client: TestClient) -> None:
        """POST /api/config/epis updates which EPIs are active."""
        resp = client.post(
            "/api/config/epis",
            json={"active_epis": ["capacete", "luvas"]},
        )
        assert resp.status_code == 200

        data = resp.json()
        active_items = [item for item in data["epis"] if item["active"]]
        active_keys = {item["key"] for item in active_items}
        assert active_keys == {"capacete", "luvas"}

        # Reset for other tests
        client.post("/api/config/epis", json={"active_epis": []})

    def test_post_epi_config_invalid_key(self, client: TestClient) -> None:
        """POST with invalid EPI key returns 400."""
        resp = client.post(
            "/api/config/epis",
            json={"active_epis": ["invalid_epi"]},
        )
        assert resp.status_code == 400
