"""Tests for Garmin login/mfa API routes (mocked garmin client)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dynamicrunner.garmin.client import LoginResult, LoginStatus, MfaResult
from tests.auth_fixtures import make_access_token


@pytest.fixture
def auth_headers(client, rsa_keys):
    private_pem, _ = rsa_keys
    token = make_access_token(private_pem)
    return {"Authorization": f"Bearer {token}"}


class TestGarminLogin:
    @patch("dynamicrunner.api.routes.garmin._update_garmin_profile")
    @patch("dynamicrunner.api.routes.garmin._store_tokens")
    @patch("dynamicrunner.api.routes.garmin.login")
    def test_login_success(self, mock_login, mock_store, mock_profile, client, auth_headers):
        mock_login.return_value = LoginResult(
            status=LoginStatus.SUCCESS,
            tokens_json=b'{"test": "tokens"}',
            garmin_user_id="testuser",
        )
        resp = client.post(
            "/garmin/login",
            json={"email": "user@example.com", "password": "pass123"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["garmin_user_id"] == "testuser"
        mock_store.assert_called_once()
        mock_profile.assert_called_once()

    @patch("dynamicrunner.api.routes.garmin.login")
    def test_login_mfa_required(self, mock_login, client, auth_headers):
        mock_login.return_value = LoginResult(status=LoginStatus.MFA_REQUIRED)
        resp = client.post(
            "/garmin/login",
            json={"email": "user@example.com", "password": "pass123"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "mfa_required"

    @patch("dynamicrunner.api.routes.garmin.login")
    def test_login_invalid_credentials(self, mock_login, client, auth_headers):
        mock_login.return_value = LoginResult(
            status=LoginStatus.INVALID_CREDENTIALS,
            error_message="Invalid email or password",
        )
        resp = client.post(
            "/garmin/login",
            json={"email": "user@example.com", "password": "wrong"},
            headers=auth_headers,
        )
        assert resp.status_code == 401
        assert "Invalid" in resp.json()["detail"]

    @patch("dynamicrunner.api.routes.garmin.login")
    def test_login_rate_limited(self, mock_login, client, auth_headers):
        mock_login.return_value = LoginResult(
            status=LoginStatus.RATE_LIMITED,
            error_message="Rate limited",
        )
        resp = client.post(
            "/garmin/login",
            json={"email": "user@example.com", "password": "pass"},
            headers=auth_headers,
        )
        assert resp.status_code == 429

    def test_login_requires_auth(self, client):
        resp = client.post(
            "/garmin/login",
            json={"email": "user@example.com", "password": "pass"},
        )
        assert resp.status_code == 401


class TestGarminMfa:
    @patch("dynamicrunner.api.routes.garmin._update_garmin_profile")
    @patch("dynamicrunner.api.routes.garmin._store_tokens")
    @patch("dynamicrunner.api.routes.garmin.complete_mfa")
    def test_mfa_success(self, mock_mfa, mock_store, mock_profile, client, auth_headers):
        mock_mfa.return_value = MfaResult(
            status=LoginStatus.SUCCESS,
            tokens_json=b'{"test": "tokens"}',
            garmin_user_id="testuser",
        )
        resp = client.post(
            "/garmin/mfa",
            json={"email": "user@example.com", "password": "pass123", "mfa_code": "123456"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    @patch("dynamicrunner.api.routes.garmin.complete_mfa")
    def test_mfa_invalid_code(self, mock_mfa, client, auth_headers):
        mock_mfa.return_value = MfaResult(
            status=LoginStatus.INVALID_CREDENTIALS,
            error_message="MFA code rejected",
        )
        resp = client.post(
            "/garmin/mfa",
            json={"email": "user@example.com", "password": "pass123", "mfa_code": "000000"},
            headers=auth_headers,
        )
        assert resp.status_code == 401
        assert "rejected" in resp.json()["detail"]

    def test_mfa_requires_auth(self, client):
        resp = client.post(
            "/garmin/mfa",
            json={"email": "user@example.com", "password": "pass", "mfa_code": "123456"},
        )
        assert resp.status_code == 401


class TestGarminDisconnect:
    @patch("dynamicrunner.api.routes.garmin.httpx.patch")
    @patch("dynamicrunner.api.routes.garmin.GarminCredentialStore")
    def test_disconnect_without_data_deletion(self, mock_store_cls, mock_patch, client, auth_headers):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store

        mock_patch.return_value = MagicMock(status_code=200)

        resp = client.delete("/garmin", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "disconnected"
        assert data["deleted_credentials"] is True
        assert data["deleted_activities"] == 0
        assert data["deleted_metrics"] == 0
        mock_store.delete_tokens.assert_called_once()

    @patch("dynamicrunner.api.routes.garmin.httpx.delete")
    @patch("dynamicrunner.api.routes.garmin.httpx.head")
    @patch("dynamicrunner.api.routes.garmin.httpx.patch")
    @patch("dynamicrunner.api.routes.garmin.GarminCredentialStore")
    def test_disconnect_with_data_deletion(
        self, mock_store_cls, mock_patch, mock_head, mock_delete, client, auth_headers
    ):
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_patch.return_value = MagicMock(status_code=200)

        # Mock HEAD responses with content-range
        head_activities = MagicMock()
        head_activities.headers = {"content-range": "0-9/42"}
        head_metrics = MagicMock()
        head_metrics.headers = {"content-range": "0-9/90"}
        mock_head.side_effect = [head_activities, head_metrics]

        mock_delete.return_value = MagicMock(status_code=200)

        resp = client.delete("/garmin?delete_data=true", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted_activities"] == 42
        assert data["deleted_metrics"] == 90

    def test_disconnect_requires_auth(self, client):
        resp = client.delete("/garmin")
        assert resp.status_code == 401
