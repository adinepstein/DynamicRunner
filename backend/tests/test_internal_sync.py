"""Tests for internal sync endpoints (cron-secret auth)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dynamicrunner.api.app import create_app
from dynamicrunner.config import Settings

TEST_CRON_SECRET = "test-cron-secret-12345"


def _make_settings(cron_secret: str = TEST_CRON_SECRET) -> Settings:
    """Create Settings manually bypassing .env file."""
    s = Settings.__new__(Settings)
    object.__setattr__(s, "__dict__", {
        "supabase_url": "https://test.supabase.co",
        "supabase_service_role_key": "test-key",
        "supabase_jwt_audience": "authenticated",
        "app_encryption_key": "dGVzdA==",
        "cron_secret": cron_secret,
        "log_level": "DEBUG",
        "log_json": False,
    })
    object.__setattr__(s, "__pydantic_fields_set__", set())
    return s


@pytest.fixture
def sync_settings():
    return _make_settings()


@pytest.fixture
def sync_client(sync_settings):
    """Test client with CRON_SECRET configured."""
    with patch("dynamicrunner.api.routes.internal.get_settings", return_value=sync_settings):
        app = create_app(settings=sync_settings, verifier_factory=lambda: None)
        yield TestClient(app)


@pytest.fixture
def cron_headers():
    return {"Authorization": f"Bearer {TEST_CRON_SECRET}"}


class TestSyncAuth:
    def test_missing_token_rejected(self, sync_client, sync_settings):
        with patch("dynamicrunner.api.routes.internal.get_settings", return_value=sync_settings):
            resp = sync_client.post("/internal/sync")
        assert resp.status_code == 401

    def test_wrong_token_rejected(self, sync_client, sync_settings):
        with patch("dynamicrunner.api.routes.internal.get_settings", return_value=sync_settings):
            resp = sync_client.post(
                "/internal/sync",
                headers={"Authorization": "Bearer wrong-secret"},
            )
        assert resp.status_code == 401

    def test_no_cron_secret_configured(self):
        no_cron = _make_settings(cron_secret="")
        with patch("dynamicrunner.api.routes.internal.get_settings", return_value=no_cron):
            app = create_app(settings=no_cron, verifier_factory=lambda: None)
            client = TestClient(app)
            resp = client.post(
                "/internal/sync",
                headers={"Authorization": "Bearer anything"},
            )
        assert resp.status_code == 503


class TestSyncAll:
    def test_no_users(self, sync_client, sync_settings, cron_headers):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("dynamicrunner.api.routes.internal.get_settings", return_value=sync_settings),
            patch("dynamicrunner.api.routes.internal.httpx.get", return_value=mock_resp),
        ):
            resp = sync_client.post("/internal/sync", headers=cron_headers)
        assert resp.status_code == 200
        assert resp.json()["synced"] == 0

    def test_syncs_users(self, sync_client, sync_settings, cron_headers):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"user_id": "user-1"},
            {"user_id": "user-2"},
        ]
        mock_resp.raise_for_status = MagicMock()

        with (
            patch("dynamicrunner.api.routes.internal.get_settings", return_value=sync_settings),
            patch("dynamicrunner.api.routes.internal.httpx.get", return_value=mock_resp),
            patch("dynamicrunner.api.routes.internal.run_backfill") as mock_bf,
        ):
            mock_bf.return_value = {"activities": 1, "daily_metrics": 2}
            resp = sync_client.post("/internal/sync", headers=cron_headers)
        assert resp.status_code == 200
        assert resp.json()["synced"] == 2


class TestSyncUser:
    def test_sync_specific_user(self, sync_client, sync_settings, cron_headers):
        with (
            patch("dynamicrunner.api.routes.internal.get_settings", return_value=sync_settings),
            patch("dynamicrunner.api.routes.internal.run_backfill") as mock_bf,
        ):
            mock_bf.return_value = {"activities": 3, "daily_metrics": 2}
            resp = sync_client.post("/internal/sync/user-123", headers=cron_headers)
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "user-123"
        assert resp.json()["days"] == 2

    def test_requires_cron_secret(self, sync_client, sync_settings):
        with patch("dynamicrunner.api.routes.internal.get_settings", return_value=sync_settings):
            resp = sync_client.post("/internal/sync/user-123")
        assert resp.status_code == 401
