"""Tests for the Garmin backfill service and endpoint."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from dynamicrunner.garmin.backfill import (
    BackfillError,
    TokenExpiredError,
    _fetch_activities,
    _fetch_daily_metrics,
    _upsert_activities,
    _upsert_daily_metrics,
    run_backfill,
)
from tests.auth_fixtures import make_access_token


@pytest.fixture
def auth_headers(client, rsa_keys):
    private_pem, _ = rsa_keys
    token = make_access_token(private_pem)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_settings():
    """Create mock settings for backfill tests."""
    settings = MagicMock()
    settings.supabase_url = "https://test.supabase.co"
    settings.supabase_service_role_key = "test-service-role-key"
    settings.app_encryption_key = "dGVzdC1rZXktMzItYnl0ZXMtbG9uZy1lbm91Z2g="
    return settings


class TestFetchActivities:
    @patch("dynamicrunner.garmin.backfill._safe_get")
    @patch("dynamicrunner.garmin.backfill.time.sleep")
    def test_single_page(self, mock_sleep, mock_get):
        mock_get.return_value = [
            {"activityId": 1, "startTimeLocal": "2026-05-01 08:00:00"},
            {"activityId": 2, "startTimeLocal": "2026-05-02 09:00:00"},
        ]
        client = MagicMock()
        result = _fetch_activities(client, date(2026, 3, 1), date(2026, 5, 30))
        assert len(result) == 2
        assert result[0]["activityId"] == 1

    @patch("dynamicrunner.garmin.backfill._safe_get")
    @patch("dynamicrunner.garmin.backfill.time.sleep")
    def test_pagination(self, mock_sleep, mock_get):
        page1 = [{"activityId": i, "startTimeLocal": "2026-05-01"} for i in range(50)]
        page2 = [{"activityId": i + 50, "startTimeLocal": "2026-05-01"} for i in range(10)]
        mock_get.side_effect = [page1, page2]

        client = MagicMock()
        result = _fetch_activities(client, date(2026, 3, 1), date(2026, 5, 30))
        assert len(result) == 60

    @patch("dynamicrunner.garmin.backfill._safe_get")
    @patch("dynamicrunner.garmin.backfill.time.sleep")
    def test_empty_response(self, mock_sleep, mock_get):
        mock_get.return_value = None
        client = MagicMock()
        result = _fetch_activities(client, date(2026, 3, 1), date(2026, 5, 30))
        assert result == []

    @patch("dynamicrunner.garmin.backfill._safe_get")
    @patch("dynamicrunner.garmin.backfill.time.sleep")
    def test_token_expired_propagates(self, mock_sleep, mock_get):
        mock_get.side_effect = TokenExpiredError("Token expired")
        client = MagicMock()
        with pytest.raises(TokenExpiredError):
            _fetch_activities(client, date(2026, 3, 1), date(2026, 5, 30))


class TestFetchDailyMetrics:
    @patch("dynamicrunner.garmin.backfill._safe_get")
    def test_full_metrics(self, mock_get):
        mock_get.side_effect = [
            {
                "totalSteps": 8000,
                "restingHeartRate": 55,
                "sleepingSeconds": 28800,
                "bodyBatteryHighestValue": 85,
                "bodyBatteryLowestValue": 20,
                "averageStressLevel": 35,
            },
            {"hrvSummary": {"lastNightAvg": 52}},
        ]
        client = MagicMock()
        result = _fetch_daily_metrics(client, date(2026, 5, 1))
        assert result is not None
        assert result["steps"] == 8000
        assert result["resting_hr"] == 55
        assert result["hrv_last_night_avg"] == 52
        assert result["date"] == "2026-05-01"

    @patch("dynamicrunner.garmin.backfill._safe_get")
    def test_no_summary_returns_none(self, mock_get):
        mock_get.return_value = None
        client = MagicMock()
        result = _fetch_daily_metrics(client, date(2026, 5, 1))
        assert result is None


class TestUpsertActivities:
    @patch("dynamicrunner.garmin.backfill.httpx.post")
    def test_upsert_batch(self, mock_post, mock_settings):
        mock_post.return_value = MagicMock(status_code=201)
        mock_post.return_value.raise_for_status = MagicMock()

        activities = [
            {"activityId": "123", "startTimeLocal": "2026-05-01 08:00:00", "distance": 5000},
            {"activityId": "456", "startTimeLocal": "2026-05-02 09:00:00", "distance": 10000},
        ]
        count = _upsert_activities(mock_settings, "user-123", activities)
        assert count == 2
        mock_post.assert_called_once()

    def test_empty_activities(self, mock_settings):
        count = _upsert_activities(mock_settings, "user-123", [])
        assert count == 0

    @patch("dynamicrunner.garmin.backfill.httpx.post")
    def test_skips_missing_id(self, mock_post, mock_settings):
        mock_post.return_value = MagicMock(status_code=201)
        mock_post.return_value.raise_for_status = MagicMock()

        activities = [
            {"startTimeLocal": "2026-05-01 08:00:00"},  # no activityId
            {"activityId": "456", "startTimeLocal": "2026-05-02 09:00:00"},
        ]
        count = _upsert_activities(mock_settings, "user-123", activities)
        assert count == 1


class TestUpsertDailyMetrics:
    @patch("dynamicrunner.garmin.backfill.httpx.post")
    def test_upsert_metrics(self, mock_post, mock_settings):
        mock_post.return_value = MagicMock(status_code=201)
        mock_post.return_value.raise_for_status = MagicMock()

        metrics = [
            {"date": "2026-05-01", "steps": 8000},
            {"date": "2026-05-02", "steps": 9000},
        ]
        count = _upsert_daily_metrics(mock_settings, "user-123", metrics)
        assert count == 2


class TestRunBackfill:
    @patch("dynamicrunner.garmin.backfill._mark_sync_complete")
    @patch("dynamicrunner.garmin.backfill._upsert_daily_metrics")
    @patch("dynamicrunner.garmin.backfill._fetch_daily_metrics")
    @patch("dynamicrunner.garmin.backfill._upsert_activities")
    @patch("dynamicrunner.garmin.backfill._fetch_activities")
    @patch("dynamicrunner.garmin.backfill._update_backfill_progress")
    @patch("dynamicrunner.garmin.backfill._restore_garth_client")
    @patch("dynamicrunner.garmin.backfill.GarminCredentialStore")
    def test_full_backfill(
        self,
        mock_store_cls,
        mock_restore,
        mock_progress,
        mock_fetch_act,
        mock_upsert_act,
        mock_fetch_daily,
        mock_upsert_daily,
        mock_complete,
        mock_settings,
    ):
        mock_store = MagicMock()
        mock_store.load_tokens.return_value = MagicMock()
        mock_store_cls.return_value = mock_store

        mock_restore.return_value = MagicMock()
        mock_fetch_act.return_value = [{"activityId": "1", "startTimeLocal": "2026-05-01"}]
        mock_upsert_act.return_value = 1
        mock_fetch_daily.return_value = {"date": "2026-05-01", "steps": 5000}
        mock_upsert_daily.return_value = 7

        result = run_backfill(mock_settings, "user-123", days=7)
        assert result["activities"] == 1
        assert result["daily_metrics"] == 7
        mock_complete.assert_called_once()

    @patch("dynamicrunner.garmin.backfill._mark_sync_error")
    @patch("dynamicrunner.garmin.backfill.GarminCredentialStore")
    def test_no_credentials(self, mock_store_cls, mock_error, mock_settings):
        mock_store = MagicMock()
        mock_store.load_tokens.return_value = None
        mock_store_cls.return_value = mock_store

        with pytest.raises(BackfillError, match="No stored"):
            run_backfill(mock_settings, "user-123")
        mock_error.assert_called_once()


class TestBackfillEndpoint:
    @patch("dynamicrunner.api.routes.garmin.run_backfill")
    @patch("dynamicrunner.api.routes.garmin.GarminCredentialStore")
    def test_backfill_started(self, mock_store_cls, mock_backfill, client, auth_headers):
        mock_store = MagicMock()
        mock_store.load_tokens.return_value = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_backfill.return_value = {"activities": 5, "daily_metrics": 30}

        resp = client.post("/garmin/backfill", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"

    @patch("dynamicrunner.api.routes.garmin.GarminCredentialStore")
    def test_backfill_no_credentials(self, mock_store_cls, client, auth_headers):
        mock_store = MagicMock()
        mock_store.load_tokens.return_value = None
        mock_store_cls.return_value = mock_store

        resp = client.post("/garmin/backfill", headers=auth_headers)
        assert resp.status_code == 400
        assert "link your account" in resp.json()["detail"]

    def test_backfill_requires_auth(self, client):
        resp = client.post("/garmin/backfill")
        assert resp.status_code == 401
