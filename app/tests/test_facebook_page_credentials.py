from __future__ import annotations

import os

from app.tests.test_api import build_client


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


def test_facebook_page_creation_rejects_user_tokens(tmp_path, monkeypatch):
    with build_client(tmp_path, env={"FACEBOOK_CREDENTIAL_VALIDATION_ENABLED": "true"}) as client:
        from app.services import facebook_credentials

        def fake_get(url, params=None, timeout=None):  # noqa: ARG001
            return _FakeResponse(
                {
                    "data": {
                        "is_valid": True,
                        "type": "USER",
                        "profile_id": "966755213194914",
                        "scopes": ["pages_messaging"],
                        "granular_scopes": [
                            {"scope": "pages_messaging", "target_ids": ["966755213194914"]},
                        ],
                    }
                }
            )

        monkeypatch.setattr(facebook_credentials.httpx, "get", fake_get)

        platform_headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=platform_headers,
            json={"name": "Facebook Credential Brand", "slug": "facebook-credential-brand"},
        )
        assert brand.status_code == 200

        page = client.post(
            "/api/v1/facebook-pages",
            headers=platform_headers,
            json={
                "brand_id": brand.json()["id"],
                "page_name": "Facebook Credential Page",
                "page_id": "966755213194914",
                "app_id": "meta-app-1",
                "app_secret": "super-secret",
                "page_access_token": "user-token-by-mistake",
                "verify_token": "verify-token-1",
            },
        )
        assert page.status_code == 400
        assert "PAGE token" in page.json()["detail"]


def test_facebook_page_creation_accepts_valid_page_tokens(tmp_path, monkeypatch):
    with build_client(tmp_path, env={"FACEBOOK_CREDENTIAL_VALIDATION_ENABLED": "true"}) as client:
        from app.services import facebook_credentials

        def fake_get(url, params=None, timeout=None):  # noqa: ARG001
            return _FakeResponse(
                {
                    "data": {
                        "is_valid": True,
                        "type": "PAGE",
                        "profile_id": "966755213194914",
                        "scopes": ["pages_messaging"],
                    }
                }
            )

        monkeypatch.setattr(facebook_credentials.httpx, "get", fake_get)

        platform_headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=platform_headers,
            json={"name": "Facebook Credential Brand 2", "slug": "facebook-credential-brand-2"},
        )
        assert brand.status_code == 200

        page = client.post(
            "/api/v1/facebook-pages",
            headers=platform_headers,
            json={
                "brand_id": brand.json()["id"],
                "page_name": "Facebook Credential Page",
                "page_id": "966755213194914",
                "app_id": "meta-app-1",
                "app_secret": "super-secret",
                "page_access_token": "actual-page-token",
                "verify_token": "verify-token-1",
            },
        )
        assert page.status_code == 200
        assert page.json()["page_id"] == "966755213194914"


def test_facebook_page_can_be_deleted(tmp_path):
    with build_client(tmp_path) as client:
        platform_headers = {"X-Platform-Token": "test-platform-token"}
        brand = client.post(
            "/api/v1/brands",
            headers=platform_headers,
            json={"name": "Facebook Delete Brand", "slug": "facebook-delete-brand"},
        )
        assert brand.status_code == 200

        page = client.post(
            "/api/v1/facebook-pages",
            headers=platform_headers,
            json={
                "brand_id": brand.json()["id"],
                "page_name": "Facebook Delete Page",
                "page_id": "966755213194915",
                "app_id": "meta-app-1",
                "app_secret": "super-secret",
                "page_access_token": "actual-page-token",
                "verify_token": "verify-token-delete",
            },
        )
        assert page.status_code == 200

        deleted = client.delete(
            f"/api/v1/facebook-pages/{page.json()['id']}",
            headers=platform_headers,
        )
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted"}

        missing = client.get(
            f"/api/v1/facebook-pages/{page.json()['id']}",
            headers=platform_headers,
        )
        assert missing.status_code == 404
